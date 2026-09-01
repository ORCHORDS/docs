# Support Multi Language Response Translation Quality Loop

## Scope

This article governs the quality loop that the support desk operates when it answers a customer in a language that the agent does not write natively. The loop covers translation, post-translation review, feedback to the translator or translation tool, and the periodic quality review that closes the loop. It applies to every channel that produces a written response in a language other than the agent's working language: chat, in-product messaging, email, knowledge article authoring, and outbound notifications.

The discipline draws on ISO 17100, which sets requirements for translation services, particularly the principle that translation quality is not a single artefact but a process that includes a translator, a reviewer, and a domain expert where the content is technical. In the support context, the domain expert is the agent who knows the case; the translator is a person or tool that produces the language-pair output; the reviewer is a second pass that confirms the translation is fit for the customer.

## Workflow or implementation guidance

The translation loop begins with a source-language draft that the agent has authored. The draft is sent to the translation step, which may be a human translator, a machine translation system, or a hybrid. The translation step returns a target-language draft that preserves the meaning, the tone, and the actionable specifics (case identifier, date, time, follow-up instructions) of the source. The target draft is then reviewed by the agent or by a designated reviewer before it is sent to the customer.

Where the translation is produced by a machine, the agent applies a defined post-editing checklist. The checklist covers: domain terminology (does the translation use the customer's industry term, not the generic word), currency and date format (does it use the customer's locale, not the agent's), named entities (is the customer's name rendered correctly, in the right script), action items (are the verbs in the imperative, not the indicative, where appropriate), and tone (is the register appropriate for the channel and the relationship). The checklist is not exhaustive; the agent applies professional judgement.

Where the translation is produced by a human translator, the loop is similar but the post-editing checklist is shorter and focuses on domain accuracy and customer-specific terminology. The agent has a defined time budget for the review; a review that exceeds the budget is escalated to a senior agent or to a translation specialist who can adjudicate.

Feedback is captured at every step. The agent records a confidence score for the translation they sent. The customer records a satisfaction signal (a thumbs-up or a follow-up correction). The signals are aggregated per language pair, per agent, and per topic. Topics that consistently produce low confidence or low satisfaction are flagged for attention; the attention may take the form of a glossary update, a translator retraining, or a change to the source-language draft that the agent produces.

## Controls

Three controls protect the loop. The first is a glossary that pairs domain terms with their approved translations in every supported language. The glossary is owned by a domain expert and is consulted by the translator or the machine translation system. Where the glossary is consulted, the translation is more likely to be accurate; where the glossary is bypassed, the translation drifts.

The second control is a periodic review of the loop's outcomes. The review examines the confidence scores, the satisfaction signals, the post-editing effort, and the rate of customer corrections. The review identifies whether a translator, a topic, or a language pair needs attention. The review produces a named action list with owners and dates.

The third control is a quality gate on outbound content that carries legal or regulatory weight. Translations of legally binding content (refund commitments, settlement terms, regulatory disclosures) must be reviewed by a qualified human reviewer, regardless of the source of the machine translation. The review is documented, and the reviewer identifier is recorded with the outbound content.

## Validation evidence

Validation evidence is collected continuously. The confidence scores and the satisfaction signals are aggregated into a per-language-pair dashboard. The glossary updates are logged with the proposing party, the approving party, and the date. The quality-gate reviews are logged with the reviewer identifier and the artifact identifier. A periodic sampling review pulls a small set of recent outbound translations and confirms that the glossary was consulted, the post-editing checklist was applied, and the customer-specific terminology was rendered correctly.

## Failure modes and correction

The most common failure is the silent bypass of the glossary. The translator or the machine translation system reverts to a generic translation that the glossary would have caught. The correction is the glossary consultation enforced at the tool layer: the translation tool surfaces the glossary entry and asks the translator to confirm or override.

The second most common failure is the agent sending a translation without applying the post-editing checklist. The correction is a workflow gate that blocks the outbound send until the agent has recorded a confidence score. The score is not a quality score of the agent; it is a quality signal of the translation that the loop uses to detect drift.

The third most common failure is the unsupported language pair. A customer writes in a language the desk cannot answer in, and the agent uses the closest available translator without flagging the limitation. The correction is a defined fallback: the desk tells the customer the supported languages, offers a callback in a supported language, or accepts the case in the customer's language and acknowledges that the response may be slower.

## Limitations

The discipline assumes that the supported languages are bounded and that the support desk can commit to a quality bar in each. Where the language set is large or the volume per language is small, the cost of maintaining a glossary and a review regime may exceed the value. The discipline should be applied in proportion to the language set and the regulatory environment.

## Canonical sources

- ISO 17100:2015/Amd 1:2017, Translation services — Requirements for translation services (publisher and title only; ISO standards pages return access-controlled responses to automated clients).
- W3C, Internationalization resources, https://www.w3.org/International/
- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ENISA, Risk Management Resources, https://www.enisa.europa.eu/topics/risk-management