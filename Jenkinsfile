pipeline {
    agent any
    
    parameters {
        string(name: 'ENVIRONMENT', defaultValue: 'dev', description: 'Environment to deploy to (dev, stage, prod)')
        booleanParam(name: 'CLEAN_BUILD', defaultValue: true, description: 'Clean workspace before build?')
    }
    
    stages {
        stage('Checkout') {
            steps {
                script {
                    checkout scm
                }
            }
        }
        
        stage('Build') {
            steps {
                sh 'echo "Building in ${ENVIRONMENT} environment"'
                sh 'echo "Clean build: ${CLEAN_BUILD}"'
                // Your build steps here
            }
        }
        
        stage('Deploy') {
            when {
                expression { params.ENVIRONMENT == 'stage' }
            }
            steps {
                sh 'echo "Deploying to stage environment"'
                // Your deployment steps here
            }
        }
    }
}
