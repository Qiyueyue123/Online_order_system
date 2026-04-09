import uuid
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from .db import (
    InventoryError,
    add_product_image,
    create_product,
    create_order,
    delete_product,
    delete_product_image,
    get_admin_user_by_username,
    get_homepage_alert,
    get_menu_items,
    get_order,
    get_preparation_style_choices,
    get_product_with_images,
    list_orders,
    list_stock_pools,
    update_homepage_alert,
    update_product,
    update_product_image_order,
    update_stock_pool,
)


bp = Blueprint("main", __name__)
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
PICKUP_WINDOW_DAYS = 5
PICKUP_START_HOUR = 16
PICKUP_END_HOUR = 21
PICKUP_INTERVAL_MINUTES = 30


def admin_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("main.admin_login"))
        return view(**kwargs)

    return wrapped_view


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
    for day_offset in range(PICKUP_WINDOW_DAYS):
        day = (reference + timedelta(days=day_offset)).date()
        day_start = datetime.combine(day, datetime.min.time()).replace(hour=PICKUP_START_HOUR)
        day_end = datetime.combine(day, datetime.min.time()).replace(hour=PICKUP_END_HOUR)
        candidate = day_start
        while candidate < day_end:
            if candidate >= current:
                slots.append(
                    {
                        "value": candidate.strftime("%Y-%m-%dT%H:%M"),
                        "label": candidate.strftime("%a %d %b, %H:%M"),
                    }
                )
            candidate += timedelta(minutes=PICKUP_INTERVAL_MINUTES)
    return slots


def format_pickup_at(value):
    pickup_at = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    return pickup_at.strftime("%a %d %b, %H:%M")


def enrich_order_bundle(order_bundle):
    order = dict(order_bundle["order"])
    order["pickup_label"] = format_pickup_at(order["pickup_at"])
    return {"order": order, "items": order_bundle["items"]}


@bp.route("/")
def home():
    return render_template(
        "index.html",
        menu_items=get_menu_items(),
        homepage_alert=get_homepage_alert(),
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
        phone_last4 = request.form.get("phone_last4", "").strip()
        pickup_at = request.form.get("pickup_at", "").strip()
        payment_method = request.form.get("payment_method", "cash")
        notes = request.form.get("notes", "").strip()

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

        if not name or not phone_last4 or not pickup_at:
            flash("Name, last 4 phone digits, and pickup time are required.")
        elif pickup_at not in valid_pickup_values:
            flash("Choose one of the available pickup times.")
        else:
            try:
                order_id = create_order(
                    name=name,
                    phone_last4=phone_last4,
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
                return redirect(url_for("main.confirmation", order_id=order_id))

    return render_template(
        "checkout.html",
        menu_items=menu_items,
        preparation_styles=preparation_styles,
        pickup_slots=pickup_slots,
    )


@bp.route("/orders/<int:order_id>/confirmation")
def confirmation(order_id):
    order_bundle = get_order(order_id)
    if order_bundle is None:
        abort(404)
    return render_template("confirmation.html", order_bundle=enrich_order_bundle(order_bundle))


@bp.route("/admin")
@admin_required
def admin():
    return render_template(
        "admin.html",
        orders=[enrich_order_bundle(bundle) for bundle in list_orders()],
        stock_pools=list_stock_pools(),
        menu_items=get_menu_items(),
        homepage_alert=get_homepage_alert(),
    )


@bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_authenticated"):
        return redirect(url_for("main.admin"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        admin_user = get_admin_user_by_username(username)
        valid_password = admin_user is not None and check_password_hash(
            admin_user["password_hash"],
            password,
        )

        if valid_password:
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
    if not image_path.startswith(uploads_prefix):
        return

    filename = image_path.removeprefix(uploads_prefix)
    safe_name = Path(filename).name
    file_path = Path(current_app.config["UPLOAD_FOLDER"]) / safe_name
    if file_path.exists():
        file_path.unlink()
