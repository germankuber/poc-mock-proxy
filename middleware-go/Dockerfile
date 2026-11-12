FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY main.go ./
RUN CGO_ENABLED=0 go build -o /middleware .

FROM gcr.io/distroless/static-debian12
COPY --from=build /middleware /middleware
ENTRYPOINT ["/middleware"]
