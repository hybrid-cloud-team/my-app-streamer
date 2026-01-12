#!/bin/bash
# ECR 리포지토리가 public인지 private인지 확인하는 스크립트

# 사용법: ./check-ecr-visibility.sh <리포지토리_이름> <리전>
# 예시: ./check-ecr-visibility.sh simple_streamer us-east-1

REPO_NAME=$1
REGION=${2:-us-east-1}

if [ -z "$REPO_NAME" ]; then
    echo "사용법: $0 <리포지토리_이름> [리전]"
    echo "예시: $0 simple_streamer us-east-1"
    exit 1
fi

echo "🔍 ECR 리포지토리 확인 중: $REPO_NAME (리전: $REGION)"
echo ""

# Public 리포지토리 확인
echo "📋 Public 리포지토리 목록 확인 중..."
PUBLIC_REPOS=$(aws ecr-public describe-repositories --region us-east-1 --query "repositories[?repositoryName=='$REPO_NAME'].repositoryName" --output text 2>/dev/null)

if [ ! -z "$PUBLIC_REPOS" ]; then
    echo "✅ Public 리포지토리입니다!"
    echo "   → imagePullSecrets 불필요"
    exit 0
fi

# Private 리포지토리 확인
echo "📋 Private 리포지토리 목록 확인 중..."
PRIVATE_REPO=$(aws ecr describe-repositories --region $REGION --repository-names $REPO_NAME --query "repositories[0].repositoryName" --output text 2>/dev/null)

if [ ! -z "$PRIVATE_REPO" ] && [ "$PRIVATE_REPO" != "None" ]; then
    echo "🔒 Private 리포지토리입니다!"
    echo "   → imagePullSecrets 필요"
    exit 0
fi

echo "❌ 리포지토리를 찾을 수 없습니다."
echo "   리포지토리 이름과 리전을 확인해주세요."
