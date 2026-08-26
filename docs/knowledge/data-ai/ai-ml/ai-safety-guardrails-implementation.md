# AI Safety Guardrails Implementation

## Overview

AI safety guardrails are essential mechanisms that prevent harmful, inappropriate, or unethical outputs from AI systems. These safeguards protect users and organizations while maintaining the utility of AI applications.

## Input Filtering

Input filtering prevents malicious or inappropriate user prompts from reaching the AI system. This involves sanitizing inputs and detecting potentially dangerous patterns.

```python
import re
from typing import List

def filter_input(prompt: str) -> bool:
    """Filter out dangerous input patterns"""
    dangerous_patterns = [
        r'(\bexec\b|\bimport\b|\b__\w+__\b)',  # Python execution patterns
        r'(password|secret|token).*?(\w{3,})',  # Credential patterns
        r'(sql.*?union|drop.*?table|delete.*?from)'  # SQL injection patterns
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, prompt.lower()):
            return False
    return True

# Example usage
user_input = "Please execute system commands"
if not filter_input(user_input):
    print("Input blocked - potential security risk")
```

## Output Filtering

Output filtering monitors and modifies AI responses to prevent harmful content generation.

```python
def filter_output(response: str, banned_words: List[str]) -> str:
    """Remove or replace banned words from output"""
    filtered_response = response.lower()

    for word in banned_words:
        if word.lower() in filtered_response:
            # Replace with asterisks or remove entirely
            filtered_response = re.sub(
                r'\b' + re.escape(word.lower()) + r'\b',
                '*' * len(word),
                filtered_response
            )

    return filtered_response

# Example usage
banned_terms = ['hate', 'violence', 'discrimination']
output = "This policy promotes hate and violence"
filtered = filter_output(output, banned_terms)
print(filtered)  # This policy promotes *** and *****
```

## Toxicity Detection

Toxicity detection identifies harmful language patterns that could cause offense or harm.

```python
from transformers import pipeline

class ToxicityDetector:
    def __init__(self):
        self.detector = pipeline(
            "text-classification",
            model="unitary/toxic-bert"
        )

    def detect_toxicity(self, text: str) -> dict:
        """Detect
