import { useQuery } from "@tanstack/react-query";
import { api, formatNoticeDate, Notice } from "../api/client";

/**
 * Slim, full-width announcement strip pinned to the very top of the site.
 * Best-effort: a broken or empty notice list should never break the page,
 * so failures and empty results both render nothing.
 */
export function NoticeBanner() {
  const notices = useQuery({
    queryKey: ["notices"],
    queryFn: () => api<Notice[]>("/notices"),
    retry: false,
  });
  if (!notices.data || notices.data.length === 0) return null;
  return (
    <section className="notice-banner" aria-label="Shop notices">
      {notices.data.map((notice) => (
        <p className="notice-banner-row" key={notice.id}>
          <span className="notice-banner-title">{notice.title}</span>
          <span className="notice-banner-body">{notice.body}</span>
          <span className="notice-banner-date">{formatNoticeDate(notice.created_at)}</span>
        </p>
      ))}
    </section>
  );
}
