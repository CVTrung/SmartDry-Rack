from typing import Annotated

from fastapi import APIRouter, Depends

from backend.auth_dependency import get_current_account


router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/auth/me")
def get_authenticated_account(
    account: Annotated[dict, Depends(get_current_account)],
):
    return account
