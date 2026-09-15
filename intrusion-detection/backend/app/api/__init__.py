from fastapi import APIRouter

from . import datasets, detections, experiments, models, reports

api_router = APIRouter()
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(experiments.router, prefix="/experiments", tags=["experiments"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(detections.router, prefix="/detections", tags=["detections"])
api_router.include_router(reports.router, prefix="/detections", tags=["reports"])