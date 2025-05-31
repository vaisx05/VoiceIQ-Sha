import re
from agents import async_groq_client

class SanitizationService:
    def __init__(self):
        self.groq_client = async_groq_client

    def _regex_filter(self, text: str) -> str:
        """Fast masking for SSNs and card numbers."""
        # Card number masking (shows first 6 and last 4)
        card_pattern = r'\b((?:\d[ -]?){6})(?:(?:[Xx\- ]{1,6}|\d[ -]?){2,9})([ -]?\d{4})\b'
        def mask_card(match):
            first = re.sub(r'\D', '', match.group(1))[:6]
            last = re.sub(r'\D', '', match.group(2))[-4:]
            masked = f"{first}{'X' * max(0, 16 - len(first) - len(last))}{last}"
            return masked
        text = re.sub(card_pattern, mask_card, text)

        # SSN masking
        ssn_pattern = r'\b(\d{3}|X{3})[- ]?(\d{2}|X{2})[- ]?(\d{4})\b'
        text = re.sub(ssn_pattern, r'XXX-XX-\3', text)

        return text

    async def sanitize(self, transcript: str) -> str:
        """
        Combines regex masking + Groq LLM-based redaction for full PII cleansing.
        """
        filtered = self._regex_filter(transcript)

        prompt = f"""
            You are a redaction assistant.

            Redact personal identifiable information (PII) such as:
            - Social Security Numbers (SSNs)
            - Credit/debit card numbers
            - Government-issued ID numbers

            Replace them with X and only expose a few digits at the start and at the end.
            
            Keep these details:
            - Names
            - Phone numbers
            - Email addresses

            Except the names that are mentioned

            Example:
            Input: Call me at 555-123-4567 or email john.doe@example.com.
            Output: Call me at 5XX-XXX-XX67 or email john.doe@example.com.

            Now redact this transcript:
            
            {filtered}
            
            Respond with the redacted transcript only do not add any headers or footers.
            """.strip()

        response = await self.groq_client.chat.completions.create(
            model="deepseek-r1-distill-llama-70b",
            reasoning_format="hidden",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        cleaned_response = re.sub(r'<think>.*?</think>', '', response.choices[0].message.content, flags=re.DOTALL)

        return cleaned_response.strip()
