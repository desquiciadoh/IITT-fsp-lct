"""Shared enums used across all Django apps in the FSP Draft platform."""

from django.db import models


class UserRole(models.TextChoices):
    CANDIDATE = "candidate", "Candidate"
    EMPLOYER = "employer", "Employer"
    ADMIN = "admin", "Admin"


class Specialization(models.TextChoices):
    BACKEND = "backend", "Backend"
    FRONTEND = "frontend", "Frontend"
    ML_DATA = "ml_data", "ML & Data"


class Grade(models.TextChoices):
    INTERN = "intern", "Intern"
    JUNIOR = "junior", "Junior"
    MIDDLE = "middle", "Middle"
    SENIOR = "senior", "Senior"


class EvidenceSource(models.TextChoices):
    TEST = "test", "Verified by test"
    FSP = "fsp", "Verified by FSP"
    MICROTASK = "microtask", "Verified by micro-task"
    DECLARED = "declared", "Declared"


class WorkFormat(models.TextChoices):
    OFFICE = "office", "Office"
    HYBRID = "hybrid", "Hybrid"
    REMOTE = "remote", "Remote"


class SalaryType(models.TextChoices):
    GROSS = "gross", "Gross"
    NET = "net", "Net"


class ItemFormat(models.TextChoices):
    CODE_OUTPUT = "code_output", "Code Output"
    FIND_BUG = "find_bug", "Find Bug"
    SQL_RESULT = "sql_result", "SQL Result"
    COMPLEXITY = "complexity", "Complexity"
    NUMERIC_SCENARIO = "numeric_scenario", "Numeric Scenario"
    CONCEPT_MCQ = "concept_mcq", "Concept MCQ"


class AssessmentKind(models.TextChoices):
    INITIAL = "initial", "Initial"
    FALLBACK = "fallback", "Fallback"
    PROMOTION = "promotion", "Promotion"
    SCREENING = "screening", "Screening"


class AssessmentMode(models.TextChoices):
    FULL = "full", "Full"
    EXPRESS = "express", "Express"


class AssessmentStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "In Progress"
    FINISHED = "finished", "Finished"
    ABANDONED = "abandoned", "Abandoned"
    EXPIRED = "expired", "Expired"


class GradeDecision(models.TextChoices):
    CONFIRMED = "confirmed", "Confirmed"
    UNCONFIRMED = "unconfirmed", "Unconfirmed"


class LeagueStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    UNCONFIRMED = "unconfirmed", "Unconfirmed"


class ItemFamilyStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    FLAGGED = "flagged", "Flagged"
    RETIRED = "retired", "Retired"


class OfferStatus(models.TextChoices):
    SENT = "sent", "Sent"
    VIEWED = "viewed", "Viewed"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    EXPIRED = "expired", "Expired"
    WITHDRAWN = "withdrawn", "Withdrawn"
    INTERVIEW = "interview", "Interview"
    HIRED = "hired", "Hired"
    CLOSED = "closed", "Closed"


class DeclineReason(models.TextChoices):
    SALARY = "salary", "Salary"
    STACK = "stack", "Stack"
    FORMAT = "format", "Format"
    COMPANY = "company", "Company"
    TIMING = "timing", "Timing"
    NOT_LOOKING = "not_looking", "Not Looking"
    OTHER = "other", "Other"


class ContactChannel(models.TextChoices):
    EMAIL = "email", "Email"
    PHONE = "phone", "Phone"
    TELEGRAM = "telegram", "Telegram"
    PLATFORM = "platform", "Platform"


class ContactGrantSource(models.TextChoices):
    OFFER = "offer", "Offer"
    APPLICATION = "application", "Application"


class TrustLevel(models.TextChoices):
    NONE = "none", "None"
    DOMAIN = "domain", "Domain verified"
    VERIFIED = "verified", "Verified"


class ConsentType(models.TextChoices):
    PROCESSING = "processing", "Processing"
    PUBLICATION = "publication", "Publication"
    FSP_SYNC = "fsp_sync", "FSP Sync"


class IdentityProvider(models.TextChoices):
    LOCAL = "local", "Local"
    FSP_ID = "fsp_id", "FSP ID"


class SyncStatus(models.TextChoices):
    OK = "ok", "OK"
    PENDING = "pending", "Pending"
    ERROR = "error", "Error"
    NOT_FOUND = "not_found", "Not Found"
    FAILED = "failed", "Failed"


class PlacementTier(models.TextChoices):
    WINNER = "winner", "Winner"
    PRIZE_WINNER = "prize_winner", "Prize Winner"
    FINALIST = "finalist", "Finalist"
    PARTICIPANT = "participant", "Participant"


class SportsRank(models.TextChoices):
    CAT3 = "cat3", "3rd Category"
    CAT2 = "cat2", "2nd Category"
    CAT1 = "cat1", "1st Category"
    KMS = "kms", "KMS"
    MS = "ms", "MS"


class Discipline(models.TextChoices):
    ALGORITHMIC = "algorithmic", "Algorithmic"
    PRODUCT = "product", "Product"
    INFOSEC = "infosec", "InfoSec"
    ROBOTICS = "robotics", "Robotics"
    UAS = "uas", "UAS"
