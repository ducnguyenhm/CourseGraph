import type { ProgramSummary, Standing } from "@/lib/api";

// Form fields shared by the record page and sign-up.

export const STANDINGS: { value: Standing; label: string }[] = [
  { value: "first_year", label: "First year" },
  { value: "sophomore", label: "Sophomore" },
  { value: "junior", label: "Junior" },
  { value: "senior", label: "Senior" },
];
export const TERMS = [
  { value: "FA", label: "Fall" },
  { value: "WI", label: "Winter Term" },
  { value: "SP", label: "Spring" },
  { value: "MY", label: "May Term" },
  { value: "SU", label: "Summer" },
];
const FIRST_YEAR = 2015;
const LAST_YEAR = 2035;

export const input = "rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm";

export function ProgramPicker({ programs, value, onChange }: { programs: ProgramSummary[]; value: string[]; onChange: (p: string[]) => void }) {
  return (
    <fieldset className="flex flex-col gap-1.5 text-sm">
      <legend className="mb-1">Declared majors and minors</legend>
      <div className="flex flex-wrap gap-2">
        {programs
          .filter((p) => p.kind !== "degree")
          .map((p) => (
            <label key={p.program_id} className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1">
              <input
                type="checkbox"
                checked={value.includes(p.program_id)}
                onChange={(e) => onChange(e.target.checked ? [...value, p.program_id] : value.filter((x) => x !== p.program_id))}
              />
              {p.name} {p.kind}
            </label>
          ))}
      </div>
    </fieldset>
  );
}

export function TermPicker({ value, onChange, only }: { value: string; onChange: (t: string) => void; only?: string[] }) {
  const year = value.slice(0, 4);
  const kind = value.slice(4);
  // Wide enough for a transfer student's first term and a late graduation;
  // a stored year outside it still shows.
  const years = Array.from({ length: LAST_YEAR - FIRST_YEAR + 1 }, (_, i) => `${FIRST_YEAR + i}`);
  if (!years.includes(year)) years.push(year);
  return (
    <span className="flex flex-wrap gap-1.5">
      <select value={kind} onChange={(e) => onChange(`${year}${e.target.value}`)} className={input} aria-label="Term">
        {TERMS.filter((t) => !only || only.includes(t.value)).map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>
      <select value={year} onChange={(e) => onChange(`${e.target.value}${kind}`)} className={input} aria-label="Year">
        {years.map((y) => (
          <option key={y}>{y}</option>
        ))}
      </select>
    </span>
  );
}

/** A term the student may leave unset; unchecking it sends null. */
export function OptionalTerm({
  value,
  fallback,
  unset,
  onChange,
}: {
  value: string | null;
  fallback: string;
  unset: string;
  onChange: (t: string | null) => void;
}) {
  return (
    <span className="flex flex-wrap items-center gap-2">
      <select value={value ? "set" : ""} onChange={(e) => onChange(e.target.value ? fallback : null)} className={input}>
        <option value="">{unset}</option>
        <option value="set">Choose…</option>
      </select>
      {value ? <TermPicker value={value} onChange={onChange} /> : null}
    </span>
  );
}
