from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db import parse_doc_id
from app.models.skill import Skill
from app.schemas.export_import import (
    ExportedSkill,
    ImportResult,
    SkillExportBundle,
    SkillImportBundle,
)
from app.schemas.skill import SkillCreate, SkillResponse, SkillUpdate

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _to_response(skill: Skill) -> SkillResponse:
    return SkillResponse(
        id=str(skill.id),
        name=skill.name,
        description=skill.description,
        instructions=skill.instructions,
        tags=skill.tags,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(body: SkillCreate, _user=Depends(get_current_user)):
    skill = Skill(**body.model_dump())
    await skill.insert()
    return _to_response(skill)


@router.get("", response_model=list[SkillResponse])
async def list_skills(_user=Depends(get_current_user)):
    skills = await Skill.find_all().to_list()
    return [_to_response(s) for s in skills]


def _to_exported(skill: Skill) -> ExportedSkill:
    return ExportedSkill(
        name=skill.name,
        description=skill.description,
        instructions=skill.instructions,
        tags=skill.tags,
    )


@router.get("/export", response_model=SkillExportBundle)
async def export_skills(_user=Depends(get_current_user)):
    skills = await Skill.find_all().to_list()
    return SkillExportBundle(items=[_to_exported(s) for s in skills])


@router.get("/{skill_id}/export", response_model=SkillExportBundle)
async def export_skill(skill_id: str, _user=Depends(get_current_user)):
    skill = await Skill.get(parse_doc_id(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillExportBundle(items=[_to_exported(skill)])


@router.post("/import", response_model=ImportResult, status_code=201)
async def import_skills(body: SkillImportBundle, _user=Depends(get_current_user)):
    result = ImportResult()
    for item in body.items:
        try:
            skill = Skill(**item.model_dump())
            await skill.insert()
            result.ids.append(str(skill.id))
            result.created += 1
        except Exception as exc:
            result.errors.append(f"{item.name}: {exc}")
    return result


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: str, _user=Depends(get_current_user)):
    skill = await Skill.get(parse_doc_id(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _to_response(skill)


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str, body: SkillUpdate, _user=Depends(get_current_user)
):
    skill = await Skill.get(parse_doc_id(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    update_data = body.model_dump(exclude_none=True)
    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        await skill.set(update_data)
    return _to_response(skill)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, _user=Depends(get_current_user)):
    skill = await Skill.get(parse_doc_id(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await skill.delete()
