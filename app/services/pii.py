import re

# Regex for email addresses
EMAIL_REGEX = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
)

# Regex for social handles (@username)
HANDLE_REGEX = re.compile(
    r'@[A-Za-z0-9_]+'
)

# Regex candidate for phone numbers (Indian and international formats)
# Targets patterns with optional country code, area code, spaces, hyphens, parentheses
PHONE_CANDIDATE_REGEX = re.compile(
    r'(?:\+?\d{1,3}[-.\s]*)?(?:\(?\d{2,5}\)?[-.\s]*)?\b\d{3,5}[-.\s]*\d{4,5}\b'
)

def remove_pii(text: str) -> str:
    """
    Removes email addresses, phone numbers, and @handles from text.
    Preserves numerical values like currency amounts, percentages, and years.
    """
    if not text:
        return ""

    # 1. Remove emails
    cleaned = EMAIL_REGEX.sub('', text)

    # 2. Remove @handles
    cleaned = HANDLE_REGEX.sub('', cleaned)

    # 3. Remove phone numbers (only matches with >= 10 digits to protect amounts/years)
    def _phone_filter(match):
        raw = match.group(0)
        digits = re.sub(r'\D', '', raw)
        if len(digits) >= 10:
            return ''
        return raw

    cleaned = PHONE_CANDIDATE_REGEX.sub(_phone_filter, cleaned)

    # 4. Clean extra spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned

def mask_pii(text: str, email_mask: str = '[EMAIL]', phone_mask: str = '[PHONE]', handle_mask: str = '[HANDLE]') -> str:
    """
    Replaces PII with placeholder tokens.
    """
    if not text:
        return ""

    cleaned = EMAIL_REGEX.sub(email_mask, text)
    cleaned = HANDLE_REGEX.sub(handle_mask, cleaned)

    def _phone_mask(match):
        digits = re.sub(r'\D', '', match.group(0))
        if len(digits) >= 10:
            return phone_mask
        return match.group(0)

    cleaned = PHONE_CANDIDATE_REGEX.sub(_phone_mask, cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

