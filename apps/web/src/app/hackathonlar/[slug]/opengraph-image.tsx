import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { notFound } from "next/navigation";
import { ImageResponse } from "next/og";

import { detail, eventRow, site } from "@/lib/copy";
import { getEvent, getPublishedEvents } from "@/lib/events";
import { formatDate, formatDateRange, formatPlace } from "@/lib/format";

// 1200×630 card for OpenGraph and Telegram (D-14). Deterministic: it shows only stored facts,
// never the phase or "days left", so the same event data always gives the same image.
// Satori supports flexbox only and cannot read woff2, hence the vendored Geist TTF files.

export const alt = site.ogImageAlt;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Fonts do not depend on the request: read once at module scope.
const fontDir = join(process.cwd(), "assets", "fonts");
const [regular, semiBold] = await Promise.all([
  readFile(join(fontDir, "Geist-Regular.ttf")),
  readFile(join(fontDir, "Geist-SemiBold.ttf")),
]);

const ink = "#15171c";
const muted = "#565d6b";
const brand = "#0b5c73";

export async function generateStaticParams() {
  const events = await getPublishedEvents();
  return events.map((event) => ({ slug: event.slug }));
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, maxWidth: 420 }}>
      <div style={{ fontSize: 22, color: muted }}>{label}</div>
      <div style={{ fontSize: 30, fontWeight: 600, color: ink }}>{value}</div>
    </div>
  );
}

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const event = await getEvent(slug);
  if (!event) notFound();

  const titleSize = event.title.length > 70 ? 54 : event.title.length > 40 ? 66 : 78;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "64px 72px",
          background: "#ffffff",
          borderTop: `16px solid ${brand}`,
          fontFamily: "Geist",
          color: ink,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 26, fontWeight: 600 }}>
          <div style={{ width: 18, height: 18, borderRadius: 9, background: brand }} />
          {site.name}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div
            style={{
              fontSize: titleSize,
              fontWeight: 600,
              lineHeight: 1.05,
              letterSpacing: -2,
              display: "flex",
            }}
          >
            {event.title}
          </div>
          {event.organizer ? (
            <div style={{ fontSize: 30, color: muted, display: "flex" }}>{event.organizer}</div>
          ) : null}
        </div>

        <div style={{ display: "flex", gap: 56, borderTop: "2px solid #e3e5ea", paddingTop: 28 }}>
          {event.application_deadline ? (
            <Fact label={eventRow.deadline} value={formatDate(event.application_deadline)} />
          ) : null}
          <Fact label={detail.dates} value={formatDateRange(event.start_date, event.end_date)} />
          <Fact label={detail.location} value={formatPlace(event)} />
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        { name: "Geist", data: regular, style: "normal", weight: 400 },
        { name: "Geist", data: semiBold, style: "normal", weight: 600 },
      ],
    },
  );
}
