from fastapi import APIRouter

from .routes import admin, auth, commercial, confection, configuration, costing, dashboard, design, integrations, process, products, production, quality, reports, resources


api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(resources.router)
api_router.include_router(products.router)
api_router.include_router(design.router)
api_router.include_router(costing.router)
api_router.include_router(production.router)
api_router.include_router(process.router)
api_router.include_router(confection.router)
api_router.include_router(reports.router)
api_router.include_router(quality.router)
api_router.include_router(configuration.router)
api_router.include_router(admin.router)
api_router.include_router(integrations.router)
api_router.include_router(commercial.router)
