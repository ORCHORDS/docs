# mobile-otp-sms-autofill

**Issue:** SMS one-time passwords (OTPs) remain the dominant second factor for phone-number-based login, and the difference between a good and terrible OTP experience is autofill: users who must memorize a 6-digit code and switch apps to read the SMS convert dramatically worse than users whose keyboard offers the code for one tap. But autofill only works when the SMS body, the text input, and platform heuristics all cooperate. Android requires a specific message format and hash for its SMS Retriever API to work without SMS permissions; iOS parses only well-formed messages against the field's textContentType. Teams that send arbitrary SMS copy (localized word order, codes with dashes, marketing appendices) silently break system autofill on both platforms and then blame the OS.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## SMS message format

1. **Keep the code plain and numeric.** Use a bare 4-8 digit code with no spaces, hyphens, or letters inside the digit group. System parsers (iOS QuickType, Android Autofill, password managers) are trained on plain digit runs; codes like "12-34-56" defeat detection.
2. **Put the code early and isolated.** Lead the message with the code or place it in a short sentence; long marketing prefixes or multiple number groups (a phone number, a price, a date) confuse extraction and can surface the wrong number in the suggestion bar.
3. **iOS: use the domain-bound format.** iOS reliably offers one-time codes when the SMS ends with a line like the domain plus code pattern — the sender domain, a separator, and the code as the final token. Format the last line as your domain and the code so both the QuickType bar and Passwords autofill trigger; also verify your domain's associated domain entitlement is configured so iOS can bind the code to your app.
4. **Android: embed the app hash for SMS Retriever.** The Play Services SMS Retriever API only captures messages that are at most 140 bytes, begin with the standard prefix token, and end with your app's 11-character hash string. Compute the hash per install (it derives from the signing certificate and package name), and append it to every verification SMS your backend sends.

## Android autofill mechanisms

1. **SMS Retriever API.** The zero-permission option: the app listens via SmsRetrieverClient, Play Services matches the hash-suffixed SMS, and delivers the whole message to the app to extract the code. No READ_SMS, no SMS permission prompts, no Play policy exposure.
2. **SMS Code Autofill hint.** For cases where the message cannot carry the hash, the SmsCodeAutofillClient / autofill hint APIs let the system fill the code into the field when the user consents — still without the SMS permission, still gated on user action.
3. **Set autofill hints on the field.** The EditText (or Compose field via its autofill interop) should carry AUTOFILL_HINT_SMS_OTP and be marked as the single OTP input. With hint set and the field focused, Android's suggestion UI fills automatically when the SMS arrives.
4. **Never request READ_SMS.** Google Play rejects READ_SMS for all but default-handler apps; reading the inbox directly is both a policy violation and a privacy anti-pattern.

## iOS autofill mechanics

1. **textContentType = .oneTimeCode.** This single line on the UITextField (or SwiftUI TextField with the textContentType modifier) is what makes iOS 12+ detect incoming codes and surface them above the keyboard. Without it, nothing else matters.
2. **Domain binding enables Passwords autofill.** With the associated domain entitlement and the domain-formatted SMS, iOS can offer the code through the QuickType bar even from the locked-state suggestion — the strongest, one-tap UX available.
3. **Do not break the field.** Custom keyboards, secure-text transformations that mangle digits, or splitting the code across six one-digit fields each disable the system suggestion. Use one field, accept paste, and render the grouping visually if you want separated digit boxes.
4. **Verify after autofill automatically.** When the field reaches expected length, submit without requiring another tap — but keep an explicit submit affordance for manual entry and autofill failure.

## Fallback UX and security

1. **Manual entry must remain first-class.** Autofill fails on rooted devices, Play Services gaps, carrier-mangled SMS, and locked-down managed devices. Show the code field, keep the keyboard numeric, and allow paste.
2. **Resend with backoff and a countdown.** One resend immediately, then a 30-60 second countdown, plus an alternate channel (voice call or WhatsApp) after repeated failure. Rate-limit sends server-side per number and per IP.
3. **Short lifetimes, single use.** Codes expire in 5-10 minutes, are single-use (reject on replay), and the server marks the phone verified — never trust client-side "code matched" state.
4. **Fire the server request with the code, not before.** Submitting phone number + code together to the verify endpoint avoids state pinning and makes retry safe across process death.
5. **WebOTP for the web surface.** In any WebView or web checkout, autocomplete="one-time-code" on the input plus a properly bound WebOTP config (WebOTP API on Android Chrome with the same SMS format, including the bound origin line) gives the same one-tap fill.
