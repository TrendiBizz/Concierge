FROM node:22-alpine
RUN apk add --no-cache ffmpeg ttf-dejavu
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY server.js ./
ENV PORT=8099
EXPOSE 8099
CMD ["node", "server.js"]
