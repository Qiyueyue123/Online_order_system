import uuid
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename

from .db import (
    InventoryError,
    add_product_image,
    add_homepage_image,
    admin_password_hash_needs_upgrade,
    can_cancel_order,
    cancel_order,
    cancel_order_by_admin,
    clear_homepage_images,
    create_product,
    create_order,
    delete_homepage_image,
    delete_order_record,
    delete_product,
    delete_product_image,
    get_admin_user_by_username,
    get_homepage_alert,
    get_menu_items,
    get_order,
    get_order_for_management,
    get_preparation_style_choices,
    get_product_with_images,
    get_site_settings,
    get_active_order_counts_by_pickup_at,
    list_pickup_days,
    list_orders,
    list_stock_pools,
    refresh_admin_user_password_hash,
    update_site_contact,
    update_homepage_alert,
    update_homepage_image_order,
    update_pickup_day,
    update_product,
    update_product_image_order,
    update_stock_pool,
    verify_admin_password_hash,
)


bp = Blueprint("main", __name__)
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
PICKUP_WINDOW_DAYS = 5
PICKUP_START_HOUR = 16
PICKUP_END_HOUR = 21
PICKUP_INTERVAL_MINUTES = 30
MAX_QUANTITY_PER_DRINK = 3
PAYMENT_METHODS = {
    "cash": "Cash on pickup",
    "manual_tikkie": "Tikkie payment request",
}
HEIF_FILE_SIGNATURES = (
    b"ftypheic",
    b"ftypheix",
    b"ftyphevc",
    b"ftyphevx",
    b"ftypmif1",
    b"ftypmsf1",
)


def admin_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("main.admin_login"))
        return view(**kwargs)

    return wrapped_view


def is_heif_upload(file_storage):
    stream = file_storage.stream
    current_position = stream.tell()
    header = stream.read(32)
    stream.seek(current_position)
    return any(signature in header for signature in HEIF_FILE_SIGNATURES)


def build_pickup_slot_choices(reference=None):
    if reference is None:
        reference = datetime.now()

    rounded_minute = ((reference.minute // PICKUP_INTERVAL_MINUTES) + 1) * PICKUP_INTERVAL_MINUTES
    current = reference.replace(second=0, microsecond=0)
    if rounded_minute >= 60:
        current = current.replace(minute=0) + timedelta(hours=1)
    else:
        current = current.replace(minute=rounded_minute)

    slots = []
    pickup_days = list_pickup_days(
        reference_date=reference.date(),
        days=PICKUP_WINDOW_DAYS,
    )
    active_order_counts = get_active_order_counts_by_pickup_at()
    for pickup_day in pickup_days:
        if not pickup_day["is_available"]:
            continue

        day = datetime.strptime(pickup_day["pickup_date"], "%Y-%m-%d").date()
        start_hour, start_minute = [int(part) for part in pickup_day["start_time"].split(":")]
        end_hour, end_minute = [int(part) for part in pickup_day["end_time"].split(":")]
        day_start = datetime.combine(day, datetime.min.time()).replace(
            hour=start_hour,
            minute=start_minute,
        )
        day_end = datetime.combine(day, datetime.min.time()).replace(
            hour=end_hour,
            minute=end_minute,
        )
        candidate = day_start
        while candidate < day_end:
            value = candidate.strftime("%Y-%m-%dT%H:%M")
            remaining_capacity = pickup_day["slot_capacity"] - active_order_counts.get(value, 0)
            if candidate >= current and remaining_capacity > 0:
                slots.append(
                    {
                        "value": value,
                        "label": candidate.strftime("%a %d %b, %H:%M"),
                        "remaining_capacity": remaining_capacity,
                    }
                )
            candidate += timedelta(minutes=PICKUP_INTERVAL_MINUTES)
    return slots


def format_pickup_at(value):
    if not value:
        return "Pickup time unavailable"
    pickup_at = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    return pickup_at.strftime("%a %d %b, %H:%M")


def enrich_order_bundle(order_bundle, cancel_token=None):
    order = dict(order_bundle["order"])
    order["pickup_label"] = format_pickup_at(order["pickup_at"])
    order["payment_label"] = PAYMENT_METHODS.get(
        order["payment_method"],
        order["payment_method"].replace("_", " ").title(),
    )
    order["can_cancel"] = can_cancel_order(order)
    return {
        "order": order,
        "items": order_bundle["items"],
        "cancel_token": cancel_token,
    }


def is_admin_history_order(order, reference=None):
    if reference is None:
        reference = datetime.now()
    if order["status"] == "cancelled":
        return True
    try:
        pickup_at = datetime.strptime(order["pickup_at"], "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return False
    return pickup_at < reference


def split_admin_orders(order_bundles, reference=None):
    if reference is None:
        reference = datetime.now()

    live_orders = []
    history_orders = []
    for order_bundle in order_bundles:
        enriched_bundle = enrich_order_bundle(order_bundle)
        order = enriched_bundle["order"]
        order["can_delete_record"] = is_admin_history_order(
            order,
            reference=reference,
        )
        if order["can_delete_record"]:
            history_orders.append(enriched_bundle)
        else:
            live_orders.append(enriched_bundle)
    return live_orders, history_orders


@bp.route("/")
def home():
    site_settings = get_site_settings()
    return render_template(
        "index.html",
        menu_items=get_menu_items(),
        homepage_alert=site_settings["homepage_alert"],
        site_settings=site_settings,
    )


@bp.route("/drinks/<int:product_id>")
def drink_detail(product_id):
    product_bundle = get_product_with_images(product_id)
    if product_bundle is None:
        abort(404)
    return render_template("drink_detail.html", product_bundle=product_bundle)


@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    menu_items = get_menu_items()
    preparation_styles = get_preparation_style_choices()
    pickup_slots = build_pickup_slot_choices()

    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()
        customer_contact = request.form.get("customer_contact", "").strip()
        pickup_at = request.form.get("pickup_at", "").strip()
        payment_method = request.form.get("payment_method", "cash")
        notes = request.form.get("notes", "").strip()
        if payment_method not in PAYMENT_METHODS:
            payment_method = "cash"

        quantities = {}
        for item in menu_items:
            raw_quantity = request.form.get(f"quantity_{item['id']}", "0").strip()
            preparation_style = request.form.get(
                f"preparation_style_{item['id']}",
                "type_1",
            )
            try:
                quantity = int(raw_quantity or 0)
            except ValueError:
                quantity = 0
            if quantity > 0:
                quantities[item["id"]] = {
                    "quantity": quantity,
                    "preparation_style": preparation_style,
                }

        valid_pickup_values = {slot["value"] for slot in pickup_slots}

        if not name or not customer_contact or not pickup_at:
            flash("Name, contact, and pickup time are required.")
        elif pickup_at not in valid_pickup_values:
            flash("Choose one of the available pickup times.")
        else:
            try:
                order_access = create_order(
                    name=name,
                    customer_contact=customer_contact,
                    pickup_at=pickup_at,
                    payment_method=payment_method,
                    notes=notes,
                    items=quantities,
                )
            except InventoryError as exc:
                flash(str(exc))
            except ValueError as exc:
                flash(str(exc) if str(exc) else "Select at least one drink before placing the order.")
            else:
                return redirect(
                    url_for(
                        "main.confirmation",
                        order_id=order_access["order_id"],
                        token=order_access["cancel_token"],
                    )
                )

    return render_template(
        "checkout.html",
        menu_items=menu_items,
        preparation_styles=preparation_styles,
        pickup_slots=pickup_slots,
        quantity_choices=range(0, MAX_QUANTITY_PER_DRINK + 1),
        max_quantity_per_drink=MAX_QUANTITY_PER_DRINK,
        payment_methods=PAYMENT_METHODS,
    )


@bp.route("/orders/<int:order_id>/confirmation")
def confirmation(order_id):
    cancel_token = request.args.get("token", "")
    order_bundle = get_order(order_id)
    if order_bundle is None:
        abort(404)
    return render_template(
        "confirmation.html",
        order_bundle=enrich_order_bundle(order_bundle, cancel_token=cancel_token),
    )


@bp.route("/orders/<int:order_id>/manage/<token>")
def manage_order(order_id, token):
    order_bundle = get_order_for_management(order_id, token)
    if order_bundle is None:
        abort(404)
    return render_template(
        "manage_order.html",
        order_bundle=enrich_order_bundle(order_bundle, cancel_token=token),
    )


@bp.route("/orders/<int:order_id>/cancel/<token>", methods=["POST"])
def cancel_order_route(order_id, token):
    result = cancel_order(order_id, token)
    if result == "not_found":
        abort(404)
    if result == "not_allowed":
        flash("This order can no longer be cancelled online. Please inform us by WhatsApp/Telegram.")
    else:
        flash("Order cancelled. Thank you for informing us in advance.")
    return redirect(url_for("main.manage_order", order_id=order_id, token=token))


@bp.route("/admin")
@admin_required
def admin():
    live_orders, history_orders = split_admin_orders(list_orders())
    return render_template(
        "admin.html",
        live_orders=live_orders,
        history_orders=history_orders,
        order_count=len(live_orders) + len(history_orders),
        stock_pools=list_stock_pools(),
        pickup_days=list_pickup_days(days=PICKUP_WINDOW_DAYS),
        menu_items=get_menu_items(),
        homepage_alert=get_homepage_alert(),
        site_settings=get_site_settings(),
    )


@bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_authenticated"):
        return redirect(url_for("main.admin"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        admin_user = get_admin_user_by_username(username)
        valid_password = admin_user is not None and verify_admin_password_hash(
            admin_user["password_hash"],
            password,
        )

        if valid_password:
            if admin_password_hash_needs_upgrade(admin_user["password_hash"]):
                refresh_admin_user_password_hash(admin_user["id"], password)
            session.clear()
            session["admin_authenticated"] = True
            session["admin_username"] = admin_user["username"]
            session["admin_user_id"] = admin_user["id"]
            return redirect(url_for("main.admin"))

        flash("Invalid login details.")

    return render_template("admin_login.html")


@bp.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("main.admin_login"))


@bp.route("/admin/site-alert", methods=["POST"])
@admin_required
def update_site_alert():
    message = request.form.get("homepage_alert", "").strip()
    update_homepage_alert(message)
    flash("Homepage alert updated." if message else "Homepage alert cleared.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/site-contact", methods=["POST"])
@admin_required
def update_admin_site_contact():
    contact_line = request.form.get("contact_line", "").strip()
    contact_phone = request.form.get("contact_phone", "").strip()
    update_site_contact(contact_line, contact_phone)
    flash("Contact details updated.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/site-homepage-image", methods=["POST"])
@admin_required
def update_admin_homepage_image():
    file = request.files.get("image_file")
    alt_text = request.form.get("alt_text", "").strip()

    if file is None or file.filename == "":
        flash("Choose an image file to upload.")
        return redirect(url_for("main.admin"))

    original_name = secure_filename(file.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        flash("Only image files such as JPG, PNG, WEBP, GIF, or SVG are allowed.")
        return redirect(url_for("main.admin"))
    if is_heif_upload(file):
        flash("HEIC or HEIF images must be converted to JPG, PNG, WEBP, GIF, or SVG before upload.")
        return redirect(url_for("main.admin"))

    if not alt_text:
        alt_text = "Homepage matcha showcase image"

    saved_name = f"{uuid.uuid4().hex}{extension}"
    destination = Path(current_app.config["UPLOAD_FOLDER"]) / saved_name
    file.save(destination)

    image_path = url_for("main.uploaded_file", filename=saved_name)
    add_homepage_image(image_path=image_path, alt_text=alt_text)
    flash("Homepage image added.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/site-homepage-images/order", methods=["POST"])
@admin_required
def reorder_admin_homepage_images():
    image_sort_orders = {}
    for key, value in request.form.items():
        if not key.startswith("sort_order_"):
            continue
        try:
            image_id = int(key.removeprefix("sort_order_"))
            sort_order = int(value)
        except ValueError:
            continue
        image_sort_orders[image_id] = sort_order

    if not image_sort_orders:
        flash("No homepage image order changes were submitted.")
        return redirect(url_for("main.admin"))

    update_homepage_image_order(image_sort_orders=image_sort_orders)
    flash("Homepage image order updated.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/site-homepage-images/<int:image_id>/delete", methods=["POST"])
@admin_required
def delete_admin_homepage_image(image_id):
    try:
        image = delete_homepage_image(image_id)
    except ValueError as exc:
        flash(str(exc))
    else:
        _delete_uploaded_file_if_local(image["image_path"])
        flash("Homepage image deleted.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/site-homepage-images/clear", methods=["POST"])
@admin_required
def clear_admin_homepage_image():
    deleted_image_paths = clear_homepage_images()
    for image_path in deleted_image_paths:
        _delete_uploaded_file_if_local(image_path)
    flash("Homepage images reset to default.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/pickup-days/<int:pickup_day_id>", methods=["POST"])
@admin_required
def update_admin_pickup_day(pickup_day_id):
    is_available = request.form.get("is_available") == "on"
    start_time = request.form.get("start_time", "").strip()
    end_time = request.form.get("end_time", "").strip()
    try:
        slot_capacity = int(request.form.get("slot_capacity", "2"))
        update_pickup_day(
            pickup_day_id=pickup_day_id,
            is_available=is_available,
            start_time=start_time,
            end_time=end_time,
            slot_capacity=slot_capacity,
        )
    except ValueError as exc:
        flash(str(exc))
    else:
        flash("Pickup availability updated.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/orders/<int:order_id>/cancel", methods=["POST"])
@admin_required
def cancel_order_admin(order_id):
    result = cancel_order_by_admin(order_id)
    if result == "not_found":
        abort(404)
    if result == "not_allowed":
        flash("Only new orders can be cancelled.")
    else:
        flash("Order cancelled and stock restored.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/orders/<int:order_id>/delete", methods=["POST"])
@admin_required
def delete_order_admin(order_id):
    result = delete_order_record(order_id)
    if result == "not_found":
        abort(404)
    if result == "not_allowed":
        flash("Only cancelled or past orders can be deleted.")
    else:
        flash("Order record deleted.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/stock-pools/<int:stock_pool_id>", methods=["POST"])
@admin_required
def update_stock(stock_pool_id):
    try:
        servings_available = int(request.form.get("servings_available", "0"))
        grams_per_serving = int(request.form.get("grams_per_serving", "0"))
        update_stock_pool(
            stock_pool_id=stock_pool_id,
            servings_available=servings_available,
            grams_per_serving=grams_per_serving,
        )
    except ValueError as exc:
        flash(str(exc) if str(exc) else "Enter valid stock values.")
    else:
        flash("Stock updated.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/products", methods=["POST"])
@admin_required
def create_product_admin():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    try:
        price_eur = float(request.form.get("price_eur", "0"))
        stock_pool_id = int(request.form.get("stock_pool_id", "0"))
    except ValueError:
        flash("Enter a valid price and stock pool.")
        return redirect(url_for("main.admin"))

    if not name or not description:
        flash("Name and description are required.")
        return redirect(url_for("main.admin"))

    try:
        create_product(
            name=name,
            price_eur=price_eur,
            description=description,
            stock_pool_id=stock_pool_id,
        )
    except ValueError as exc:
        flash(str(exc))
    else:
        flash("Drink created.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/products/<int:product_id>", methods=["POST"])
@admin_required
def update_product_admin(product_id):
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    try:
        price_eur = float(request.form.get("price_eur", "0"))
        stock_pool_id = int(request.form.get("stock_pool_id", "0"))
    except ValueError:
        flash("Enter a valid price and stock pool.")
        return redirect(url_for("main.admin"))

    if not name or not description:
        flash("Name and description are required.")
        return redirect(url_for("main.admin"))

    try:
        update_product(
            product_id=product_id,
            name=name,
            price_eur=price_eur,
            description=description,
            stock_pool_id=stock_pool_id,
        )
    except ValueError as exc:
        flash(str(exc))
    else:
        flash("Drink updated.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def delete_product_admin(product_id):
    try:
        deleted_image_paths = delete_product(product_id)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for("main.admin"))

    for image_path in deleted_image_paths:
        _delete_uploaded_file_if_local(image_path)

    flash("Drink deleted.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/products/<int:product_id>/images", methods=["POST"])
@admin_required
def upload_product_image(product_id):
    file = request.files.get("image_file")
    alt_text = request.form.get("alt_text", "").strip()

    if file is None or file.filename == "":
        flash("Choose an image file to upload.")
        return redirect(url_for("main.admin"))

    original_name = secure_filename(file.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        flash("Only image files such as JPG, PNG, WEBP, GIF, or SVG are allowed.")
        return redirect(url_for("main.admin"))
    if is_heif_upload(file):
        flash("HEIC or HEIF images must be converted to JPG, PNG, WEBP, GIF, or SVG before upload.")
        return redirect(url_for("main.admin"))

    if not alt_text:
        alt_text = f"Drink image for product {product_id}"

    saved_name = f"{uuid.uuid4().hex}{extension}"
    destination = Path(current_app.config["UPLOAD_FOLDER"]) / saved_name
    file.save(destination)

    add_product_image(
        product_id=product_id,
        image_path=url_for("main.uploaded_file", filename=saved_name),
        alt_text=alt_text,
    )
    flash("Image uploaded.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/products/<int:product_id>/images/order", methods=["POST"])
@admin_required
def reorder_product_images(product_id):
    image_sort_orders = {}
    for key, value in request.form.items():
        if not key.startswith("sort_order_"):
            continue
        try:
            image_id = int(key.removeprefix("sort_order_"))
            sort_order = int(value)
        except ValueError:
            continue
        image_sort_orders[image_id] = sort_order

    if not image_sort_orders:
        flash("No image order changes were submitted.")
        return redirect(url_for("main.admin"))

    update_product_image_order(product_id=product_id, image_sort_orders=image_sort_orders)
    flash("Image order updated.")
    return redirect(url_for("main.admin"))


@bp.route("/admin/images/<int:image_id>/delete", methods=["POST"])
@admin_required
def delete_product_image_admin(image_id):
    try:
        image = delete_product_image(image_id)
    except ValueError as exc:
        flash(str(exc))
    else:
        _delete_uploaded_file_if_local(image["image_path"])
        flash("Image deleted.")
    return redirect(url_for("main.admin"))


@bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@bp.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


def _delete_uploaded_file_if_local(image_path):
    uploads_prefix = "/uploads/"
    if not image_path:
        return
    if not image_path.startswith(uploads_prefix):
        return

    filename = image_path.removeprefix(uploads_prefix)
    safe_name = Path(filename).name
    file_path = Path(current_app.config["UPLOAD_FOLDER"]) / safe_name
    if file_path.exists():
        file_path.unlink()
