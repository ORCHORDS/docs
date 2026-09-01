# Output Toxicity Classifier Fallback Under the OWASP LLM Top 10

## Scope

An agent's output is the artifact the world sees. Even when an upstream model has been trained to refuse toxic outputs, agents operating in long, multi-turn, retrieval-rich contexts have shown that safety behavior is conditional: it can degrade under prompt pressure, retrieval contamination, or instruction replay. The OWASP LLM Top 10 treats output handling as a distinct mitigation category because the output surface is what the user, downstream system, and adversary experience.

This article covers the fallback path when an output-side safety check is needed beyond what model-level refusals can guarantee. The taxonomy here borrows the OWASP framing of layered defenses and applies it to agent systems where output flows through tool calls, retrieval citations, and user channels.

## Workflow or implementation guidance

1. Define the output categories that require classification. Refusal, partial refusal, qualified response, safe content, and unsafe content are typical categories, but they must be enumerated with examples and reviewed for the deployment context. A category list composed by intuition underrepresents edge cases.
2. Apply classification on the actual output surface, not on the model's pre-decoded intent. The agent runtime sees text after the model has decided; pre-decoded intent is unavailable in most deployments, and post-hoc classification is what operators can act on.
3. Use a fallback classifier only as a layered control. Primary reliance on model-level refusals is acceptable only when their behavior is empirically stable under the operating conditions. The fallback exists precisely because that stability is uncertain.
4. Treat classifier outputs as signals, not as verdicts. A flag should trigger downstream action - redaction, refusal to surface, escalation, alternative phrasing - rather than a hard block on every flagged case. Hard blocks on every flag produce high false-positive rates that train operators to disable the control.
5. Apply the classifier at every output boundary, not only at the user channel. Tool call output that another tool consumes, retrieval-augmented text passed downstream, and asynchronous notifications are all output surfaces where toxicity matters. Limiting classification to the user channel leaves a wide open side door.
6. Retain classification results in the audit log alongside the output. When a flagged output reaches the user, the audit log should make the flag visible. When a flagged output was suppressed, the audit log should record the suppression with reason.
7. Calibrate on representative deployment data, not on a generic test set. Classifier accuracy on synthetic hate speech differs from accuracy on the deployment's actual user population and content. Recalibrate on a defined cadence and on trigger events such as incident response.
8. Maintain a degraded mode when the classifier is unavailable. Operating without classification should require explicit authorization and an elevated review cadence, not be the silent default. The boundary between "operational" and "running without the control" must be visible to operators.

## Controls

Classifier access must be governed. A classifier that operators can disable at will is not a control; require approval to disable, with an expiry and a documented reason. Where classifier service is shared, segregate it from agent execution such that a classifier outage cannot be exploited as a control bypass.

Version the classifier and the policy together. Changing the classifier thresholds without documenting the change leaves the audit log unable to explain why a particular output was classified the way it was at a particular time. Maintain a versioned policy that maps threshold values to permitted output categories.

Quality control on the classifier is continuous. Maintain a labeled set for evaluation, including cases that should be flagged, cases that should pass, and cases that are contested. Run periodic evaluation against this set and track metrics over time. A classifier whose metrics silently degrade is a control that has stopped working.

## Validation evidence

Demonstrate the positive path: an output in a known-safe category passes classification and surfaces unchanged. Demonstrate the negative path: an output that should be flagged is flagged, with a downstream action taken and the action logged. Demonstrate boundary cases: outputs near the threshold behave consistently across runs, and the threshold itself is documented.

Demonstrate classifier unavailability behavior. With the classifier unavailable, the system runs in degraded mode with elevated review, not silent normal operation. Demonstrate that the transition into and out of degraded mode is logged with reason and that operators are alerted.

Show classifier quality over time. Periodic evaluation results are retained, the trend is visible, and classifier changes are correlated with metric changes. Show that classifier deployment is reviewable: an operator can explain why a particular output received the classification it did at the time it did.

## Failure modes and correction

The dominant failure is reliance on the classifier as the sole defense. A classifier can be evaded by paraphrase, by code-switching, by output rendering choices, and by adversaries who test the classifier directly. Correct by combining classifier output with upstream refusals, retrieval-source controls, output filtering, and human review for sensitive cases.

A second failure is threshold drift that no one notices. Operators tune the threshold for low false positives and gradually forget that false negatives are rising. Correct by tracking false-negative estimates on a labeled set and alerting on movement.

A subtler failure is classifier output ignored because of poor integration. The classifier flags content, but the downstream action is poorly specified or absent, and the flag is logged and forgotten. Correct by specifying the action for each flag category and verifying in integration tests that the action is actually taken.

## Limitations

Classifiers lag adversaries, and an adversary who targets the deployed classifier can degrade its accuracy before the deployment notices. Classifier accuracy on novel content categories is poor until sufficient labeled data is available. Multi-modal output - images, audio, code - expands the surface the classifier must cover. Output handling also raises accessibility and localization considerations that a general-purpose classifier does not address, and those require additional review rather than classifier tuning.

## Canonical sources

- **OWASP, Top 10 for Large Language Model Applications (LLM05 and LLM02 categories):** https://owasp.org/www-project-top-10-for-large-language-model-applications/
- **OWASP GenAI Security Project, LLM Top 10 (2025 edition):** https://genai.owasp.org/owasp-top-10-for-llm-applications-2025/
- **OWASP Cheat Sheet Series, Injection Prevention (defense-in-depth framing):** https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html
