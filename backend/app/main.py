from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import advising, auth, courses, graph, health, plans, programs, signup, students
from app.config import settings

app = FastAPI(
    title="CourseGraph API",
    description="Prerequisite graph and degree planner for the DePauw catalog.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Writes: a student's own record, their plan, advisor comments.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(courses.router)
app.include_router(graph.router)
app.include_router(programs.router)
app.include_router(students.router)
app.include_router(auth.router)
app.include_router(signup.router)
app.include_router(plans.router)
app.include_router(advising.router)
