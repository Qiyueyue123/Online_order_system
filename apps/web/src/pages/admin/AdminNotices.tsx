import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import {
  AdminNotice,
  AdminNoticeIn,
  AdminNoticeUpdateIn,
  api,
  formatNoticeDate,
  humanizeError,
} from "../../api/client";

type NewNoticeFields = {
  title: string;
  body: string;
};

function NoticeRow({
  notice,
  disabled,
  onSave,
  onToggle,
  onDelete,
}: {
  notice: AdminNotice;
  disabled: boolean;
  onSave: (id: string, body: AdminNoticeUpdateIn) => void;
  onToggle: (notice: AdminNotice) => void;
  onDelete: (notice: AdminNotice) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(notice.title);
  const [body, setBody] = useState(notice.body);

  function save() {
    onSave(notice.id, { title, body });
    setEditing(false);
  }

  return (
    <article className={`notice-admin-card${notice.active ? "" : " notice-admin-card--hidden"}`}>
      <div className="notice-heading">
        {editing ? (
          <input
            aria-label="Notice title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        ) : (
          <h3>{notice.title}</h3>
        )}
        <span className="notice-date">
          {notice.active ? "Visible" : "Hidden"} · posted {formatNoticeDate(notice.created_at)}
        </span>
      </div>
      {editing ? (
        <textarea
          aria-label="Notice body"
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
      ) : (
        <p>{notice.body}</p>
      )}
      <div className="notice-admin-actions">
        {editing ? (
          <>
            <button disabled={disabled} onClick={save}>Save</button>
            <button
              disabled={disabled}
              onClick={() => {
                setTitle(notice.title);
                setBody(notice.body);
                setEditing(false);
              }}
            >
              Cancel
            </button>
          </>
        ) : (
          <button disabled={disabled} onClick={() => setEditing(true)}>Edit</button>
        )}
        <button disabled={disabled} onClick={() => onToggle(notice)}>
          {notice.active ? "Hide" : "Show"}
        </button>
        <button disabled={disabled} onClick={() => onDelete(notice)}>Delete</button>
      </div>
    </article>
  );
}

export function AdminNotices({ csrfToken }: { csrfToken: string }) {
  const queryClient = useQueryClient();
  const notices = useQuery({
    queryKey: ["admin", "notices"],
    queryFn: () => api<AdminNotice[]>("/admin/notices"),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "notices"] });

  const createNotice = useMutation({
    mutationFn: (body: AdminNoticeIn) =>
      api<AdminNotice>("/admin/notices", {
        method: "POST",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      invalidate();
      reset();
    },
  });

  const updateNotice = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AdminNoticeUpdateIn }) =>
      api<AdminNotice>(`/admin/notices/${id}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });

  const deleteNotice = useMutation({
    mutationFn: (id: string) =>
      api<void>(`/admin/notices/${id}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": csrfToken },
      }),
    onSuccess: invalidate,
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<NewNoticeFields>();

  function submitNewNotice(fields: NewNoticeFields) {
    createNotice.mutate({ title: fields.title, body: fields.body });
  }

  function requestDelete(notice: AdminNotice) {
    if (!window.confirm(`Delete the notice "${notice.title}"? This can't be undone.`)) return;
    deleteNotice.mutate(notice.id);
  }

  const pending = updateNotice.isPending || deleteNotice.isPending;

  return (
    <div className="admin-notices">
      {notices.isLoading && <p role="status">Loading notices…</p>}
      {createNotice.isError && <p role="alert">{humanizeError(createNotice.error)}</p>}
      {updateNotice.isError && <p role="alert">{humanizeError(updateNotice.error)}</p>}
      {deleteNotice.isError && <p role="alert">{humanizeError(deleteNotice.error)}</p>}

      <div className="notice-admin-list">
        {notices.data?.map((notice) => (
          <NoticeRow
            key={notice.id}
            notice={notice}
            disabled={pending}
            onSave={(id, body) => updateNotice.mutate({ id, body })}
            onToggle={(target) => updateNotice.mutate({ id: target.id, body: { active: !target.active } })}
            onDelete={requestDelete}
          />
        ))}
      </div>
      {notices.data?.length === 0 && <p>No notices yet — post one below to greet visitors across the site.</p>}

      <h2>Post a notice</h2>
      <form onSubmit={handleSubmit(submitNewNotice)}>
        <label>
          Title
          <input {...register("title", { required: true })} />
        </label>
        {errors.title && <span role="alert">Title is required.</span>}
        <label>
          Message
          <textarea {...register("body", { required: true })} />
        </label>
        {errors.body && <span role="alert">Message is required.</span>}
        <button className="button" disabled={createNotice.isPending}>
          {createNotice.isPending ? "Posting…" : "Post notice"}
        </button>
      </form>
    </div>
  );
}
