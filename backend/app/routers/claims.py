"""Claims (§5.2, §5.4). Owner: Habib."""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Query, status

from ..deps import ActiveUser, CurrentUser, OfficerUser
from ..models.common import ClaimStatus
from ..schemas.claim import ClaimCreate, ClaimOut, ClaimPage, HandoverIn, Questions, ReviewNote
from ..services import claim_service

router = APIRouter(prefix="/api/claims", tags=["claims"])
questions_router = APIRouter(prefix="/api/items", tags=["claims"])

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=50)]


@questions_router.get("/{item_id}/questions", response_model=Questions,
                      summary="Verification questions for a found item (to start a claim)")
async def get_item_questions(item_id: PydanticObjectId, user: ActiveUser) -> Questions:
    return await claim_service.questions_for(item_id, user)


@router.post("", response_model=ClaimOut, status_code=status.HTTP_201_CREATED,
             summary="Claim a found item (400 on wrong answers; the third wrong set locks the claim)")
async def create_claim(data: ClaimCreate, user: ActiveUser) -> ClaimOut:
    return await claim_service.to_out(await claim_service.submit(data, user), user)


@router.get("/mine", response_model=ClaimPage, summary="My claims, newest first")
async def list_my_claims(user: CurrentUser, page: Page = 1, pageSize: PageSize = 20) -> ClaimPage:
    return await claim_service.list_mine(user, page, pageSize)


@router.get("/review", response_model=ClaimPage, summary="Officer queue, oldest first")
async def list_claims_for_review(officer: OfficerUser,
                                 status: ClaimStatus = ClaimStatus.pending,
                                 page: Page = 1, pageSize: PageSize = 20) -> ClaimPage:
    return await claim_service.review_queue(officer, status, page, pageSize)


@router.get("/{claim_id}", response_model=ClaimOut, summary="One claim (its claimant or an officer)")
async def get_claim(claim_id: PydanticObjectId, user: CurrentUser) -> ClaimOut:
    return await claim_service.to_out(await claim_service.get_for(claim_id, user), user)


@router.post("/{claim_id}/withdraw", response_model=ClaimOut, summary="Withdraw my pending claim")
async def withdraw_claim(claim_id: PydanticObjectId, user: ActiveUser) -> ClaimOut:
    return await claim_service.to_out(await claim_service.withdraw(claim_id, user), user)


@router.post("/{claim_id}/approve", response_model=ClaimOut,
             summary="Approve a claim: releases the item in one transaction (409 if it lost a race)")
async def approve_claim(claim_id: PydanticObjectId, officer: OfficerUser) -> ClaimOut:
    return await claim_service.to_out(await claim_service.approve(claim_id, officer), officer)


@router.post("/{claim_id}/reject", response_model=ClaimOut, summary="Reject a pending or locked claim")
async def reject_claim(claim_id: PydanticObjectId, officer: OfficerUser, data: ReviewNote | None = None) -> ClaimOut:
    claim = await claim_service.reject(claim_id, officer, data.note if data else None)
    return await claim_service.to_out(claim, officer)


@router.post("/{claim_id}/unlock", response_model=ClaimOut, summary="Unlock a locked claim after checking in person")
async def unlock_claim(claim_id: PydanticObjectId, officer: OfficerUser) -> ClaimOut:
    return await claim_service.to_out(await claim_service.unlock(claim_id, officer), officer)


@router.post("/{claim_id}/handover", response_model=ClaimOut,
             summary="Record the handover after checking the claimant's university ID")
async def handover_claim(claim_id: PydanticObjectId, data: HandoverIn, officer: OfficerUser) -> ClaimOut:
    return await claim_service.to_out(await claim_service.handover(claim_id, data, officer), officer)
