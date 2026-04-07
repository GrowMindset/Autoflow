from fastapi import FastAPI

from .routers.workflows import router

app=FastAPI()
app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/")
def root():
    return {"message": "Welcome to the Autoflow!"}

if __name__ == "__main__":
    app.run(debug=True)