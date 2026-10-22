"""Render GitHub's measured job/step durations, including skipped lanes, as Markdown."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def seconds(item: dict[str, Any]) -> float:
    start, end = item.get("started_at"), item.get("completed_at")
    if not start or not end:
        return 0
    return max(0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())


def report(data: dict[str, Any]) -> str:
    jobs = data["jobs"]
    lines = [
        "## CI execution timings",
        "",
        "GitHub job execution time; excludes queue time. Summed runner time is not wall time or billed cost.",
        "",
        "| Job | Result | Seconds | Longest step | Step seconds |",
        "| --- | --- | ---: | --- | ---: |",
    ]
    for job in sorted(jobs, key=seconds, reverse=True):
        longest = max(job.get("steps", []), key=seconds, default={})
        step_name = longest.get("name", "—").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| [{job['name']}]({job['html_url']}) | {job['conclusion']} | {seconds(job):.0f} | "
            f"{step_name} | {seconds(longest):.0f} |"
        )
    lines += ["", f"Summed execution time: {sum(seconds(job) for job in jobs):.0f} runner-seconds."]
    return "\n".join(lines)


if __name__ == "__main__":
    print(report(json.loads(Path(sys.argv[1]).read_text())))
