from django.contrib import admin

from .models import Answer, Interview, Question


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ["candidate", "job", "status", "overall_score", "status_label", "created_at"]
    list_filter = ["status", "status_label"]
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["interview", "category", "difficulty", "order"]
    list_filter = ["category", "difficulty"]


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ["question", "score", "created_at"]
