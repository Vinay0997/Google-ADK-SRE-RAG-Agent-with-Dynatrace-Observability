FROM node:22-alpine AS build
WORKDIR /build
COPY package*.json ./
RUN npm install
COPY index.html ./
COPY src ./src
RUN npm run build

FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist /usr/share/nginx/html
EXPOSE 8080
