from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import (
    AttemptStatus,
    QuestionType,
    Test,
    TestAnswerOption,
    TestAttempt,
    TestAttemptAnswer,
    TestGrade,
    TestQuestion,
    User,
)

from sqlalchemy.orm import joinedload

def recalculate_test_scores(db: Session, test: Test) -> None:
    # Явно загружаем вопросы с ответами
    test_with_questions = (
        db.query(Test)
        .options(
            joinedload(Test.questions).joinedload(TestQuestion.answers)
        )
        .filter(Test.id == test.id)
        .first()
    )
    
    if not test_with_questions:
        test.max_score = 0
        return

    total = 0

    for question in test_with_questions.questions:
        if not question.is_active:
            question.max_score = 0
            db.flush()
            continue

        active_answers = [a for a in question.answers if a.is_active]

        if not active_answers:
            question.max_score = 0
            db.flush()
            continue

        if question.question_type == QuestionType.single_choice:
            positive_scores = [a.score for a in active_answers if a.score > 0]
            question.max_score = max(positive_scores) if positive_scores else 0
        else:
            question.max_score = sum(a.score for a in active_answers if a.score > 0)

        total += question.max_score
        db.flush()

    test.max_score = total
    db.flush()


def validate_publish(db: Session, test: Test) -> None:
    # Пересчитываем баллы перед валидацией
    recalculate_test_scores(db, test)
    
    # Явно загружаем вопросы с ответами
    test_with_questions = (
        db.query(Test)
        .options(
            joinedload(Test.questions).joinedload(TestQuestion.answers)
        )
        .filter(Test.id == test.id)
        .first()
    )

    if not test_with_questions:
        raise HTTPException(status_code=422, detail="Test not found")

    active_questions = [q for q in test_with_questions.questions if q.is_active]

    if not active_questions:
        raise HTTPException(status_code=422, detail="Test has no active questions")

    if test.max_score <= 0:
        raise HTTPException(
            status_code=422,
            detail=f"Test max score must be greater than 0 (current: {test.max_score})"
        )

    if test.passing_score > test.max_score:
        raise HTTPException(
            status_code=422,
            detail=f"Passing score ({test.passing_score}) cannot be greater than max score ({test.max_score})",
        )
    

def assert_grade_no_overlap(
    db: Session,
    test_id,
    min_score: int,
    max_score: int | None,
    exclude_id=None,
) -> None:
    query = db.query(TestGrade).filter(TestGrade.test_id == test_id)

    if exclude_id:
        query = query.filter(TestGrade.id != exclude_id)

    new_max = float("inf") if max_score is None else max_score

    for grade in query.all():
        existing_max = float("inf") if grade.max_score is None else grade.max_score

        if not (new_max < grade.min_score or existing_max < min_score):
            raise HTTPException(status_code=409, detail="Grade score ranges overlap")


def get_attempt_access(db: Session, test: Test, user: User) -> dict:
    now = datetime.now(timezone.utc)

    completed_count = (
        db.query(func.count(TestAttempt.id))
        .filter(
            TestAttempt.test_id == test.id,
            TestAttempt.user_id == user.id,
            TestAttempt.status == AttemptStatus.completed,
        )
        .scalar()
        or 0
    )

    attempts_left = None
    if test.max_attempts is not None:
        attempts_left = max(0, test.max_attempts - completed_count)

    cooldown_until = None
    can_start = True
    reason = "ok"

    if not test.is_published:
        can_start = False
        reason = "test_not_published"
    elif not user.is_active:
        can_start = False
        reason = "user_inactive"
    elif test.max_attempts is not None and completed_count >= test.max_attempts:
        can_start = False
        reason = "no_attempts_left"
    else:
        in_progress = (
            db.query(TestAttempt)
            .filter(
                TestAttempt.test_id == test.id,
                TestAttempt.user_id == user.id,
                TestAttempt.status == AttemptStatus.in_progress,
            )
            .first()
        )

        if in_progress:
            can_start = False
            reason = "attempt_in_progress"
        else:
            last_completed = (
                db.query(TestAttempt)
                .filter(
                    TestAttempt.test_id == test.id,
                    TestAttempt.user_id == user.id,
                    TestAttempt.status == AttemptStatus.completed,
                )
                .order_by(TestAttempt.completed_at.desc())
                .first()
            )

            if last_completed and test.retake_interval_minutes:
                cooldown_until = last_completed.completed_at + timedelta(
                    minutes=test.retake_interval_minutes
                )

                if now < cooldown_until:
                    can_start = False
                    reason = "retake_cooldown"

    return {
        "can_start": can_start,
        "reason": reason,
        "completed_attempts": completed_count,
        "attempts_left": attempts_left,
        "cooldown_until": cooldown_until,
    }


def complete_attempt(db: Session, attempt: TestAttempt, payload) -> TestAttempt:
    if attempt.status != AttemptStatus.in_progress:
        raise HTTPException(status_code=409, detail="Attempt is not in progress")

    test = attempt.test

    answers_by_question = {item.question_id: item for item in payload.answers}
    total_score = 0

    active_questions = [q for q in test.questions if q.is_active]

    for question in active_questions:
        submitted = answers_by_question.get(question.id)
        selected_ids = set(submitted.selected_option_ids) if submitted else set()

        options = {a.id: a for a in question.answers if a.is_active}

        invalid_ids = [sid for sid in selected_ids if sid not in options]
        if invalid_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid answer options for question {question.id}",
            )

        selected_options = [options[sid] for sid in selected_ids]

        if question.question_type == QuestionType.single_choice:
            if len(selected_options) > 1:
                raise HTTPException(
                    status_code=422,
                    detail=f"Question {question.id} expects only one answer",
                )

            score = max(0, selected_options[0].score) if selected_options else 0
        else:
            raw_score = sum(option.score for option in selected_options)
            score = min(max(raw_score, 0), question.max_score)

        total_score += score

        db.add(
            TestAttemptAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                selected_option_ids=[str(option.id) for option in selected_options],
                score=score,
                max_score=question.max_score,
            )
        )

    attempt.status = AttemptStatus.completed
    attempt.score = total_score
    attempt.max_score = test.max_score
    attempt.passing_score = (
        attempt.passing_score
        if attempt.passing_score is not None
        else test.passing_score
    )
    attempt.passed = total_score >= attempt.passing_score

    grade = (
        db.query(TestGrade)
        .filter(
            TestGrade.test_id == test.id,
            TestGrade.min_score <= total_score,
            or_(
                TestGrade.max_score.is_(None),
                TestGrade.max_score >= total_score,
            ),
        )
        .order_by(TestGrade.min_score.desc())
        .first()
    )

    attempt.grade_id = grade.id if grade else None
    attempt.grade_name = grade.name if grade else None
    attempt.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(attempt)

    return attempt