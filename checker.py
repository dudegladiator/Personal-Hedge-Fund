from openai import OpenAI

client = OpenAI(
  api_key="AIzaSyC5TSKNvjbhUfJuI_Q5GT3qxrLylxZMTKI",
  base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

models = client.models.list()
for model in models:
  print(model.id)
