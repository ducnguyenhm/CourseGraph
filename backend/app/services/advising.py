"""Who may see a plan, comment on it, and resolve the comments.

The rules alone, with no database or login: the API looks up the account and
stores what these return. An advisor sees and comments on the plans of their
assigned advisees; a student sees their own plan and the comments on it, and
is the one who marks a conversation resolved. Each comment opens a
conversation that both the student and their advisors answer in (since
2026-11-18; before that only advisors wrote), and a student may open one too,
to ask about a placement.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime

from app.services.evaluator import label
from app.services.planner import Placement

ROLES = ("student", "advisor")


class Forbidden(Exception):
    """The account may not do this. The API answers 403."""


@dataclass(frozen=True)
class Account:
    key: str  # a student's key is their student_key
    role: str  # student | advisor


@dataclass(frozen=True)
class Comment:
    student_key: str
    author: str
    body: str
    # The placement commented on; None for the plan as a whole.
    course_id: str | None
    # The term the course was in when the comment was written, so a later
    # move does not make "too early for this" read as nonsense.
    term: str | None
    resolved: bool
    created: datetime
    id: int | None = None
    # The conversation this answers; None for the comment that opened it.
    parent_id: int | None = None


class Policy:
    def __init__(
        self,
        assignments: dict[str, Iterable[str]],
        invites: dict[str, Iterable[str]] | None = None,
    ):
        """assignments: advisor key -> the student keys they advise.
        invites: advisor key -> the students they asked, still unanswered.

        The methods that change who advises whom change these in place; the
        API stores the same change."""
        self.assignments = {a: set(s) for a, s in assignments.items()}
        self.pending = {a: set(s) for a, s in (invites or {}).items()}

    def advisees(self, account: Account) -> list[str]:
        if account.role != "advisor":
            raise Forbidden("only advisors have advisees")
        return sorted(self.assignments.get(account.key, ()))

    # -- choosing advisees (2026-11-18) --------------------------------------
    # An advisor sees the whole record of everyone they advise, so adding a
    # student is a request that the student answers. Signing up with an
    # advisor is the student's own choice and needs no request.

    def _advisor(self, account: Account) -> None:
        if account.role != "advisor":
            raise Forbidden("only advisors choose advisees")

    def invite(self, account: Account, student_key: str, students: Iterable[str]) -> None:
        """students: the keys that have a student login; a record with no
        login has no one to answer."""
        self._advisor(account)
        if student_key not in set(students):
            raise ValueError(f"no student login {student_key!r}")
        if student_key in self.assignments.get(account.key, ()):
            raise ValueError(f"{student_key} is already your advisee")
        if student_key in self.pending.get(account.key, ()):
            raise ValueError(f"you already asked {student_key}; they have not answered yet")
        self.pending.setdefault(account.key, set()).add(student_key)

    def cancel_invite(self, account: Account, student_key: str) -> None:
        self._advisor(account)
        if student_key not in self.pending.get(account.key, ()):
            raise ValueError(f"no request to {student_key} to withdraw")
        self.pending[account.key].discard(student_key)

    def invites(self, account: Account) -> list[str]:
        """An advisor's unanswered requests, or the advisors asking a student."""
        if account.role == "advisor":
            return sorted(self.pending.get(account.key, ()))
        return sorted(a for a, s in self.pending.items() if account.key in s)

    def answer_invite(self, account: Account, advisor_key: str, accept: bool) -> bool:
        if account.role != "student":
            raise Forbidden("only the student asked answers a request")
        if account.key not in self.pending.get(advisor_key, ()):
            raise ValueError(f"no request from {advisor_key}")
        self.pending[advisor_key].discard(account.key)
        if accept:
            self.assignments.setdefault(advisor_key, set()).add(account.key)
        return accept

    def release(self, account: Account, student_key: str) -> None:
        """Take a student off the list. Their record and the comments stay;
        the advisor loses access, and may ask again."""
        self._advisor(account)
        if student_key not in self.assignments.get(account.key, ()):
            raise ValueError(f"{student_key} is not your advisee")
        self.assignments[account.key].discard(student_key)

    def can_view(self, account: Account, student_key: str) -> bool:
        if account.role == "student":
            return account.key == student_key
        return student_key in self.assignments.get(account.key, ())

    def comment(
        self,
        account: Account,
        student_key: str,
        plan: list[Placement],
        body: str,
        course_id: str | None = None,
    ) -> Comment:
        self._may_write(account, student_key)
        if not body.strip():
            raise ValueError("a comment needs some text")
        term = None
        if course_id is not None:
            placed = next((p for p in plan if p.course_id == course_id), None)
            if placed is None:
                raise ValueError(f"{label(course_id)} is not in the plan")
            term = placed.term
        return Comment(student_key, account.key, body.strip(), course_id, term, False, datetime.now())

    def reply(self, account: Account, parent: Comment, body: str) -> Comment:
        """An answer in `parent`'s conversation. It carries the parent's
        placement, so the answer shows beside the same course."""
        self._may_write(account, parent.student_key)
        if parent.parent_id is not None:
            raise ValueError("answer the conversation, not another answer")
        if not body.strip():
            raise ValueError("a reply needs some text")
        return Comment(
            parent.student_key,
            account.key,
            body.strip(),
            parent.course_id,
            parent.term,
            False,
            datetime.now(),
            parent_id=parent.id,
        )

    def _may_write(self, account: Account, student_key: str) -> None:
        if not self.can_view(account, student_key):
            raise Forbidden(
                f"{account.key} does not advise {student_key}"
                if account.role == "advisor"
                else "you can write only on your own plan"
            )

    def resolve(self, account: Account, comment: Comment) -> Comment:
        if comment.parent_id is not None:
            raise ValueError("resolve the conversation, not one answer in it")
        if account.role != "student" or account.key != comment.student_key:
            raise Forbidden("only the student whose plan it is resolves a comment")
        return replace(comment, resolved=True)

    def thread(self, account: Account, student_key: str, comments: Iterable[Comment]) -> list[Comment]:
        """The student's conversations, unresolved first, each group oldest
        first, each followed by its answers, oldest first."""
        if not self.can_view(account, student_key):
            raise Forbidden(f"{account.key} may not see {student_key}'s plan")
        mine = [c for c in comments if c.student_key == student_key]
        answers: dict[int | None, list[Comment]] = {}
        for c in mine:
            if c.parent_id is not None:
                answers.setdefault(c.parent_id, []).append(c)
        out: list[Comment] = []
        for root in sorted((c for c in mine if c.parent_id is None), key=lambda c: (c.resolved, c.created)):
            out.append(root)
            out.extend(sorted(answers.get(root.id, []), key=lambda c: c.created))
        return out


def awaiting_advisor(comments: Iterable[Comment]) -> int:
    """Open conversations whose last word is the student's: what the advisor
    still owes an answer to. Comments are one student's."""
    comments = list(comments)
    last: dict[int | None, Comment] = {}
    for c in sorted(comments, key=lambda c: c.created):
        last[c.parent_id if c.parent_id is not None else c.id] = c
    roots = [c for c in comments if c.parent_id is None and not c.resolved]
    return sum(1 for r in roots if last[r.id].author == r.student_key)
