# 웹 이미지: 빌드한 정적 파일을 nginx 가 서빙하고, /api/ 는 api 컨테이너로 넘긴다.
# 빌드 범위는 저장소 루트 (웹 테스트가 contracts/golden 을 읽는다). compose 가 context: . 로 부른다.
# 선박별 JSON(/data)은 이미지에 넣지 않고 compose 가 볼륨(web/public/data)으로 붙인다.
FROM node:22-alpine AS build
WORKDIR /repo/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
COPY contracts/ /repo/contracts/
RUN npm run build

FROM nginx:1.27-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/web/dist /usr/share/nginx/html
EXPOSE 80
