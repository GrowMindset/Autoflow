from fastapi import APIRouter 


router = APIRouter(
    prefix="/workflows",
    tags=["workflows"],)


@router.get("/")
def get_workflows():
    return {"message": "List of workflows"}