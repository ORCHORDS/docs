# Lesson: Deployment Permissions Should Be Separated From Build Permissions

A build job rarely needs the same privileges as a production deployment job. Separate stages so compromise in an earlier step does not automatically grant production control.

Source: GitHub Actions security guidance.