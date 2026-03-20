FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json* ./

RUN npm install

COPY . .

# Exposure port
EXPOSE 3000

# Developement mode
CMD ["npm", "run", "dev"]
