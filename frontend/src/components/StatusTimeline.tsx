import type { AppEvent } from "../api/types";
import { formatDate, STATUS_LABEL } from "../lib/format";

export function StatusTimeline({ events }: { events: AppEvent[] }) {
  if (!events.length) return <p className="text-sm text-neutral-500">Событий пока нет.</p>;
  return (
    <ol className="space-y-0">
      {events.map((event, index) => (
        <li key={event.id} className="relative border-l-2 border-[#ef3124]/30 pb-4 pl-4">
          <span className="absolute -left-[5px] top-1 h-2 w-2 rounded-full bg-[#ef3124]" />
          <p className="text-sm font-semibold">
            {event.from_status ? STATUS_LABEL[event.from_status] ?? event.from_status : "Старт"}
            {" → "}
            {STATUS_LABEL[event.to_status] ?? event.to_status}
          </p>
          <p className="text-xs text-neutral-500">
            Этап {event.application_version} · {formatDate(event.at)}
            {index === events.length - 1 ? " · текущий статус" : ""}
          </p>
        </li>
      ))}
    </ol>
  );
}
