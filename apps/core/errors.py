"""RFC 7807 Problem+JSON error handling for FSP Draft API.

All API errors are returned as application/problem+json with machine-readable
error codes, enabling frontend to handle errors programmatically.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler


# --- Custom Exception Classes ---

def normalize_errors(errors: any) -> list[dict[str, str]]:
    """Normalize any error representation to a consistent list of {field, msg} dicts."""
    if not errors:
        return []
    result = []
    if isinstance(errors, dict):
        for field, messages in errors.items():
            if isinstance(messages, list):
                for msg in messages:
                    if isinstance(msg, dict):
                        result.extend(normalize_errors(msg))
                    else:
                        result.append({'field': str(field), 'msg': str(msg)})
            elif isinstance(messages, dict):
                for subfield, submsg in messages.items():
                    result.append({'field': f"{field}.{subfield}", 'msg': str(submsg)})
            else:
                result.append({'field': str(field), 'msg': str(messages)})
    elif isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict) and 'field' in item and 'msg' in item:
                result.append({'field': str(item['field']), 'msg': str(item['msg'])})
            elif isinstance(item, dict):
                result.extend(normalize_errors(item))
            else:
                result.append({'field': '__all__', 'msg': str(item)})
    else:
        result.append({'field': '__all__', 'msg': str(errors)})
    return result


class FSPAPIError(APIException):
    """Base exception for FSP Draft API errors."""

    def __init__(
        self,
        code: str,
        title: str,
        detail: str = '',
        status_code: int = status.HTTP_400_BAD_REQUEST,
        errors: any = None,
    ):
        self.code = code
        self.title = title
        self.detail_msg = detail
        self.status_code = status_code
        self.errors_list = normalize_errors(errors) if errors else []
        super().__init__(detail=detail)


class SalaryInvalid(FSPAPIError):
    def __init__(self, detail: str = 'salary_min must be > 0 and salary_max >= salary_min'):
        super().__init__('salary_invalid', 'Invalid salary range', detail, 422)


class CooldownActive(FSPAPIError):
    def __init__(self, next_attempt_at: str = ''):
        super().__init__(
            'cooldown_active',
            'Cooldown period active',
            f'Next attempt allowed at {next_attempt_at}',
            429,
        )


class VersionConflict(FSPAPIError):
    def __init__(self):
        super().__init__(
            'version_conflict',
            'Version conflict',
            'The resource was modified by another request. Retry with the current version.',
            409,
        )


class ContactNotGranted(FSPAPIError):
    def __init__(self):
        super().__init__(
            'contact_not_granted',
            'Contact access not granted',
            'Candidate contacts are not available without an accepted offer.',
            403,
        )


class ItemNotCurrent(FSPAPIError):
    def __init__(self):
        super().__init__(
            'item_not_current',
            'Item not current',
            'This item is not the current item in the assessment session.',
            409,
        )


class InvalidTransition(FSPAPIError):
    def __init__(self, from_status: str, to_status: str):
        super().__init__(
            'invalid_transition',
            'Invalid status transition',
            f'Cannot transition from {from_status} to {to_status}.',
            409,
        )


class AssessmentInProgress(FSPAPIError):
    def __init__(self):
        super().__init__(
            'assessment_in_progress',
            'Assessment already in progress',
            'Finish or abandon the current assessment before starting a new one.',
            409,
        )


class FSPIdAlreadyLinked(FSPAPIError):
    def __init__(self):
        super().__init__(
            'fsp_id_already_linked',
            'FSP ID already linked',
            'This FSP participant ID is already linked to another account.',
            409,
        )


class CandidateNotReachable(FSPAPIError):
    def __init__(self):
        super().__init__(
            'candidate_not_reachable',
            'Candidate not reachable',
            'The candidate is not accepting offers or is not visible to your company.',
            403,
        )


# --- Exception Handler ---

def fsp_exception_handler(exc, context):
    """DRF exception handler that returns RFC 7807 problem+json responses."""

    if isinstance(exc, FSPAPIError):
        data = {
            'type': f'https://fsp-draft.local/problems/{exc.code}',
            'title': exc.title,
            'status': exc.status_code,
            'code': exc.code,
            'detail': exc.detail_msg,
        }
        if exc.errors_list:
            data['errors'] = exc.errors_list
        return Response(
            data,
            status=exc.status_code,
            content_type='application/problem+json',
        )

    if isinstance(exc, ValidationError):
        errors = normalize_errors(exc.detail)
        return Response(
            {
                'type': 'https://fsp-draft.local/problems/validation_failed',
                'title': 'Validation failed',
                'status': 422,
                'code': 'validation_failed',
                'detail': 'One or more fields failed validation.',
                'errors': errors,
            },
            status=422,
            content_type='application/problem+json',
        )

    # Fallback to DRF's default handler
    response = exception_handler(exc, context)
    if response is not None:
        code = 'api_error'
        title = 'Error'
        if response.status_code == 404:
            code = 'not_found'
            title = 'Not Found'
        elif response.status_code == 403:
            code = 'forbidden'
            title = 'Forbidden'
        elif response.status_code == 401:
            code = 'unauthorized'
            title = 'Unauthorized'
        elif response.status_code == 429:
            code = 'rate_limited'
            title = 'Rate Limited'
        elif response.status_code == 405:
            code = 'method_not_allowed'
            title = 'Method Not Allowed'
        elif response.status_code == 406:
            code = 'not_acceptable'
            title = 'Not Acceptable'
        elif response.status_code == 415:
            code = 'unsupported_media_type'
            title = 'Unsupported Media Type'

        detail = ''
        errors = []
        if isinstance(response.data, dict):
            if 'detail' in response.data:
                detail = str(response.data['detail'])
            else:
                errors = normalize_errors(response.data)
                detail = 'One or more fields failed validation.' if response.status_code in (400, 422) else title
        elif isinstance(response.data, list):
            errors = normalize_errors(response.data)
            detail = 'One or more fields failed validation.' if response.status_code in (400, 422) else title
        elif isinstance(response.data, str):
            detail = response.data

        data = {
            'type': f'https://fsp-draft.local/problems/{code}',
            'title': title,
            'status': response.status_code,
            'code': code,
            'detail': str(detail),
        }
        if errors:
            data['errors'] = errors

        error_response = Response(
            data,
            status=response.status_code,
            content_type='application/problem+json',
        )
        # Preserve important headers
        for header in ('Retry-After', 'Allow', 'WWW-Authenticate'):
            if response.has_header(header):
                error_response[header] = response[header]
        return error_response

    return None
