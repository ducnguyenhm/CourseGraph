import Link from "next/link";
import type { PrereqNode } from "@/lib/api";

/** Renders a stored expression tree as nested, readable structure. */
export function PrereqTree({
  node,
  depth = 0,
}: {
  node: PrereqNode;
  depth?: number;
}) {
  const indent = { marginLeft: depth * 14 };
  const cond = "text-warning";

  switch (node.type) {
    case "none":
      return (
        <div style={indent} className="text-muted-foreground">
          No prerequisite
        </div>
      );

    case "course":
      return (
        <div style={indent}>
          <Link
            href={`/courses/${node.course_id}`}
            className="font-mono font-medium underline-offset-2 hover:underline"
          >
            {node.course_id.replace("-", " ")}
          </Link>
          {node.min_grade ? (
            <span className="text-muted-foreground"> (min {node.min_grade})</span>
          ) : null}
        </div>
      );

    case "coreq":
      return (
        <div style={indent}>
          <Link
            href={`/courses/${node.course_id}`}
            className="font-mono font-medium underline-offset-2 hover:underline"
          >
            {node.course_id.replace("-", " ")}
          </Link>
          <span className="text-muted-foreground"> — pre- or co-requisite</span>
        </div>
      );

    case "consent":
      return (
        <div style={indent} className={cond}>
          Consent of {node.by}
        </div>
      );

    case "standing":
      return (
        <div style={indent} className={cond}>
          {node.min_level
            ? `${node.min_level.replace("_", "-")} standing or above`
            : `${node.max_level?.replace("_", "-")} students only`}
        </div>
      );

    case "course_level":
      return (
        <div style={indent} className={cond}>
          {node.count} × {node.subject} course numbered {node.min_number}+
        </div>
      );

    case "program":
      return (
        <div style={indent} className={cond}>
          Declared {node.program_id}
        </div>
      );

    case "placement":
      return (
        <div style={indent} className={cond}>
          Placement: {node.test}
        </div>
      );

    case "and":
    case "or":
      return (
        <div style={indent}>
          <span
            className={`text-[10px] font-medium uppercase tracking-wider ${
              node.type === "or" ? "text-primary" : "text-muted-foreground"
            }`}
          >
            {node.type === "or" ? "one of" : "all of"}
          </span>
          <div
            className={
              node.type === "or"
                ? "border-l border-dashed border-primary/40 pl-2"
                : "border-l border-border pl-2"
            }
          >
            {node.children.map((child, i) => (
              <PrereqTree key={i} node={child} depth={depth} />
            ))}
          </div>
        </div>
      );
  }
}
