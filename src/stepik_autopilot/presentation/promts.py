def autopilot_prompt(course_id: str, target: str = "tasks_complete") -> str:
    return (
        f"Run practical tasks for Stepik course {course_id} with target {target}. "
        "Use stepik_run_start, solve batches, commit them, collect results at each round boundary, "
        "and repair only known wrong tasks. Never mark lectures read."
    )


def resume_prompt(run_id: str) -> str:
    return f"Resume Stepik run {run_id}: inspect status, recover outstanding state, then request the next batch."


def review_prompt(course_id: str) -> str:
    return (
        f"Start course {course_id} in review mode. Save a batch, review its exact revision, "
        "then submit only the approved answers."
    )


def tutor_prompt(course_id: str) -> str:
    return f"Start course {course_id} in tutor mode. Present one practical batch at a time."
