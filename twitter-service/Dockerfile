FROM node:20-alpine
WORKDIR /app

# Install ALL deps (the service runs via tsx, which lives in devDependencies).
COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 3001
CMD ["npm", "start"]
