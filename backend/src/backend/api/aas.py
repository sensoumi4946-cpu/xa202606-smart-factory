from fastapi import APIRouter, HTTPException

from semantic_layer.aas_bridge import get_aas_catalog, get_aas_descriptor

router = APIRouter()


@router.get("/api/v1/aas")
async def list_aas():
    return {"shells": get_aas_catalog()}


@router.get("/api/v1/aas/{subsystem}")
async def get_aas(subsystem: str):
    descriptor = get_aas_descriptor(subsystem)
    if descriptor is None:
        raise HTTPException(
            status_code=404,
            detail=f"No AAS descriptor for '{subsystem}'. Valid: temp_humidity, lighting, gas, agv, counting",
        )
    return descriptor
