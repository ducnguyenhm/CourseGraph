from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import courses, graph, health, programs, students
from app.config import settings

app = FastAPI(
    title="CourseGraph API",
    description="Prerequisite graph and degree planner for the DePauw catalog.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(courses.router)
app.include_router(graph.router)
app.include_router(programs.router)
app.include_router(students.router)
