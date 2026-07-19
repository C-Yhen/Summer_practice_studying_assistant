from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from backend.app.api.v1.courses import _owned_course
from backend.app.dependencies import CurrentUser, DBSession
from backend.app.models import KnowledgeMastery, KnowledgePoint, LearningRecord, PracticeAttempt, PracticeQuestion, WrongQuestionEntry
from backend.app.responses import ok
from backend.app.schemas import PracticeAttemptCreate, WrongBookUpdate

router = APIRouter(tags=["practice"])

def _summary(db: DBSession, user_id: int, course_id: int) -> dict:
    attempts = list(db.scalars(select(PracticeAttempt).where(PracticeAttempt.user_id == user_id, PracticeAttempt.course_id == course_id)))
    correct = sum(item.is_correct for item in attempts)
    pending = db.scalar(select(func.count()).select_from(WrongQuestionEntry).where(WrongQuestionEntry.user_id == user_id, WrongQuestionEntry.course_id == course_id, WrongQuestionEntry.status == "pending")) or 0
    return {"total_attempts": len(attempts), "correct_attempts": correct, "wrong_attempts": len(attempts)-correct, "accuracy": round(correct / len(attempts), 4) if attempts else 0, "pending_wrong_count": pending, "knowledge_point_count": db.scalar(select(func.count()).select_from(KnowledgePoint).where(KnowledgePoint.course_id == course_id)) or 0}

def _question(question: PracticeQuestion, point: KnowledgePoint | None = None, *, reveal: bool = False) -> dict:
    data = {"id":question.id,"knowledge_point_id":question.knowledge_point_id,"knowledge_point":point.name if point else None,"question_type":question.question_type,"stem":question.stem,"options":question.options,"difficulty":question.difficulty,"origin":question.origin}
    if reveal: data.update({"correct_option":question.correct_option,"explanation":question.explanation,"source_page_number":question.source_page_number,"source_quote":question.source_quote})
    return data

@router.post("/courses/{course_id}/practice/questions/bootstrap")
def bootstrap(course_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    course = _owned_course(db, course_id, current_user.id)
    points = list(db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course.id).order_by(KnowledgePoint.id).limit(10)))
    created = existing = 0
    for point in points:
        key = f"rule_seed:kp:{point.id}"
        if db.scalar(select(PracticeQuestion.id).where(PracticeQuestion.course_id == course.id, PracticeQuestion.seed_key == key)):
            existing += 1; continue
        name = point.name
        db.add(PracticeQuestion(course_id=course.id, knowledge_point_id=point.id, seed_key=key, stem=f'关于知识点“{name}”，下列哪项最符合完成该知识点学习后的要求？', options=[{"key":"A","text":f"能够用自己的话解释“{name}”的核心含义，并说明基本适用场景。"},{"key":"B","text":"只浏览任务标题即可。"},{"key":"C","text":"只累计学习时长而无需理解。"},{"key":"D","text":"跳过该知识点并直接标记完成。"}], correct_option="A", explanation=point.description or f"这是课程“{course.name}”中“{name}”的规则化基础自测题。", difficulty=point.difficulty, origin="rule_seed")); created += 1
    db.commit()
    return ok({"created_count":created,"existing_count":existing,"total":created+existing,"reason":"NO_KNOWLEDGE_POINTS" if not points else None})

@router.get("/courses/{course_id}/practice/questions")
def questions(course_id: int, db: DBSession, current_user: CurrentUser, mode: str = Query("all", pattern="^(all|wrong)$"), limit: int = Query(20, ge=1, le=100), knowledge_point_id: int | None = None) -> dict:
    course = _owned_course(db, course_id, current_user.id)
    query = select(PracticeQuestion, KnowledgePoint).outerjoin(KnowledgePoint, KnowledgePoint.id == PracticeQuestion.knowledge_point_id).where(PracticeQuestion.course_id == course.id, PracticeQuestion.is_active.is_(True))
    if knowledge_point_id is not None: query = query.where(PracticeQuestion.knowledge_point_id == knowledge_point_id)
    if mode == "wrong": query = query.join(WrongQuestionEntry, WrongQuestionEntry.question_id == PracticeQuestion.id).where(WrongQuestionEntry.user_id == current_user.id, WrongQuestionEntry.status == "pending")
    rows = list(db.execute(query.order_by(PracticeQuestion.id).limit(limit)))
    return ok({"course":{"id":course.id,"name":course.name},"items":[_question(q,p) for q,p in rows],"total":len(rows),"summary":_summary(db,current_user.id,course.id)})

@router.post("/courses/{course_id}/practice/questions/{question_id}/attempts")
def attempt(course_id: int, question_id: int, payload: PracticeAttemptCreate, db: DBSession, current_user: CurrentUser) -> dict:
    _owned_course(db, course_id, current_user.id)
    old = db.scalar(select(PracticeAttempt).where(PracticeAttempt.user_id == current_user.id, PracticeAttempt.submission_id == payload.submission_id))
    if old:
        question = db.get(PracticeQuestion, old.question_id); point = db.get(KnowledgePoint, question.knowledge_point_id) if question else None
        return ok({"attempt_id":old.id,"question_id":old.question_id,"selected_option":old.selected_option,"is_correct":old.is_correct,"idempotent_replay":True,**_question(question,point,reveal=True),"summary":_summary(db,current_user.id,course_id)})
    question = db.scalar(select(PracticeQuestion).where(PracticeQuestion.id == question_id, PracticeQuestion.course_id == course_id, PracticeQuestion.is_active.is_(True)))
    if question is None: raise HTTPException(404,"QUESTION_NOT_FOUND")
    if payload.selected_option not in {str(x.get("key")) for x in question.options}: raise HTTPException(422,"INVALID_OPTION")
    correct = payload.selected_option == question.correct_option; now=datetime.now(timezone.utc)
    row=PracticeAttempt(submission_id=payload.submission_id,user_id=current_user.id,course_id=course_id,question_id=question.id,selected_option=payload.selected_option,is_correct=correct,elapsed_seconds=payload.elapsed_seconds,submitted_at=now); db.add(row)
    mastery = None
    if question.knowledge_point_id:
        mastery=db.scalar(select(KnowledgeMastery).where(KnowledgeMastery.user_id==current_user.id,KnowledgeMastery.knowledge_point_id==question.knowledge_point_id))
        if mastery is None: mastery=KnowledgeMastery(user_id=current_user.id,course_id=course_id,knowledge_point_id=question.knowledge_point_id,score=.3,confidence=.2,attempts=0,correct_attempts=0); db.add(mastery)
        mastery.attempts += 1; mastery.correct_attempts += int(correct); mastery.score=round(max(0,min(1, mastery.score + (.12*(1-mastery.score) if correct else -.10*mastery.score))),4); mastery.confidence=round(max(0,min(1,mastery.confidence + (.08 if correct else -.04))),4); mastery.last_studied_at=now
    db.add(LearningRecord(user_id=current_user.id,course_id=course_id,knowledge_point_id=question.knowledge_point_id,duration_seconds=payload.elapsed_seconds,record_type="practice",completed=True,occurred_at=now))
    entry=None
    if not correct:
        entry=db.scalar(select(WrongQuestionEntry).where(WrongQuestionEntry.user_id==current_user.id,WrongQuestionEntry.question_id==question.id))
        if entry: entry.status="pending"; entry.wrong_count+=1; entry.last_selected_option=payload.selected_option; entry.last_wrong_at=now; entry.mastered_at=None
        else: entry=WrongQuestionEntry(user_id=current_user.id,course_id=course_id,question_id=question.id,last_selected_option=payload.selected_option,last_wrong_at=now); db.add(entry)
    db.commit(); db.refresh(row); point=db.get(KnowledgePoint,question.knowledge_point_id) if question.knowledge_point_id else None
    return ok({"attempt_id":row.id,"question_id":question.id,"selected_option":row.selected_option,"is_correct":correct,"idempotent_replay":False,**_question(question,point,reveal=True),"mastery_score":mastery.score if mastery else None,"wrong_book_updated":entry is not None,"summary":_summary(db,current_user.id,course_id)})

@router.get("/courses/{course_id}/wrong-book")
def wrong_book(course_id:int,db:DBSession,current_user:CurrentUser,status:str=Query("all",pattern="^(all|pending|mastered)$"),q:str="",limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)) -> dict:
    _owned_course(db,course_id,current_user.id); query=select(WrongQuestionEntry,PracticeQuestion,KnowledgePoint,KnowledgeMastery).join(PracticeQuestion,PracticeQuestion.id==WrongQuestionEntry.question_id).outerjoin(KnowledgePoint,KnowledgePoint.id==PracticeQuestion.knowledge_point_id).outerjoin(KnowledgeMastery,(KnowledgeMastery.user_id==current_user.id)&(KnowledgeMastery.knowledge_point_id==PracticeQuestion.knowledge_point_id)).where(WrongQuestionEntry.user_id==current_user.id,WrongQuestionEntry.course_id==course_id,WrongQuestionEntry.status!="removed")
    if status!="all": query=query.where(WrongQuestionEntry.status==status)
    if q: query=query.where((PracticeQuestion.stem.ilike(f"%{q}%")) | (KnowledgePoint.name.ilike(f"%{q}%")))
    rows=list(db.execute(query.order_by(WrongQuestionEntry.last_wrong_at.desc()).offset(offset).limit(limit))); items=[{"id":e.id,"status":e.status,"wrong_count":e.wrong_count,"last_selected_option":e.last_selected_option,"last_wrong_at":e.last_wrong_at.isoformat(),"question":_question(p,k,reveal=True),"mastery_score":m.score if m else None} for e,p,k,m in rows]
    counts={s:db.scalar(select(func.count()).select_from(WrongQuestionEntry).where(WrongQuestionEntry.user_id==current_user.id,WrongQuestionEntry.course_id==course_id,WrongQuestionEntry.status==s)) or 0 for s in ("pending","mastered")}; return ok({"items":items,"total":len(items),"summary":{**counts,"repeated_wrong":sum(i["wrong_count"]>1 for i in items)}})

@router.patch("/courses/{course_id}/wrong-book/{entry_id}")
def update_wrong(entry_id:int,course_id:int,payload:WrongBookUpdate,db:DBSession,current_user:CurrentUser)->dict:
    _owned_course(db,course_id,current_user.id); entry=db.scalar(select(WrongQuestionEntry).where(WrongQuestionEntry.id==entry_id,WrongQuestionEntry.user_id==current_user.id,WrongQuestionEntry.course_id==course_id))
    if entry is None: raise HTTPException(404,"WRONG_ENTRY_NOT_FOUND")
    entry.status=payload.status; entry.mastered_at=datetime.now(timezone.utc) if payload.status=="mastered" else None; db.commit(); return ok({"id":entry.id,"status":entry.status})
