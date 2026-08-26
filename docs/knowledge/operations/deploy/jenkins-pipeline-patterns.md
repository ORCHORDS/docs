# jenkins-pipeline-patterns

**Issue:** Structuring Jenkins pipelines for reliable, maintainable CI/CD
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Freestyle Jenkins jobs are hard to version control and test. Declarative pipelines in Jenkinsfile provide reproducible, code-reviewed CI/CD definitions.

## Pattern / Solution
Declarative Jenkinsfile:
```groovy
pipeline {
  agent {
    kubernetes {
      yaml """
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: build
    image: node:20-alpine
    command: [sleep, infinity]
"""
    }
  }

  environment {
    IMAGE_TAG = "${env.GIT_COMMIT[0..7]}"
    REGISTRY  = 'ghcr.io/myorg'
  }

  options {
    timeout(time: 30, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '20'))
    disableConcurrentBuilds(abortPrevious: true)
  }

  stages {
    stage('Install') {
      steps {
        container('build') {
          sh 'npm ci'
        }
      }
    }

    stage('Test') {
      steps {
        container('build') {
          sh 'npm test -- --coverage'
        }
      }
      post {
        always {
          junit 'coverage/junit.xml'
          publishHTML([reportDir: 'coverage/lcov-report', reportFiles: 'index.html', reportName: 'Coverage'])
        }
      }
    }

    stage('Build & Push') {
      when { branch 'main' }
      steps {
        withCredentials([usernamePassword(credentialsId: 'ghcr-creds', usernameVariable: 'USER', passwordVariable: 'PASS')]) {
          sh '''
            docker build -t ${REGISTRY}/myapp:${IMAGE_TAG} .
            echo $PASS | docker login ghcr.io -u $USER --password-stdin
            docker push ${REGISTRY}/myapp:${IMAGE_TAG}
          '''
        }
      }
    }

    stage('Deploy Staging') {
      when { branch 'main' }
      steps {
        sh "helm upgrade --install myapp ./chart --set image.tag=${IMAGE_TAG} -n staging"
      }
    }

    stage('Approve Production') {
      when { branch 'main' }
      steps {
        input message: 'Deploy to production?', ok: 'Deploy'
      }
    }
  }

  post {
    failure {
      slackSend channel: '#deploys', color: 'danger', message: "Build failed: ${env.JOB_NAME} #${env.BUILD_NUMBER}"
    }
  }
}
```

## Gotchas
- `disableConcurrentBuilds(abortPrevious: true)` is essential for feature branches to avoid race conditions
- Shared libraries (`@Library('my-lib')`) must be trusted in Jenkins global security settings before use
- Kubernetes pod agents are deleted after the build; do not store artifacts on the agent filesystem
- `input` steps hold an executor; configure a timeout or use `milestone` to prevent orphaned approvals
- Never hardcode credentials; always use `withCredentials` or `credentials()` binding

## Related
- `github-actions-self-hosted.md`
- `deployment-approval-workflow.md`
- `deployment-notification-slack.md`
