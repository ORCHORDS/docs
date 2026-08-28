# Lesson: Workflow Inputs Can Be Code Injection Paths

Issue titles, branch names, PR metadata, and other untrusted strings can become script input inside CI workflows. Pass data through safe parameters or environment variables instead of interpolating it into executable script text.

Source: GitHub Actions security guidance.