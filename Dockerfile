FROM python:latest

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/

CMD python3 /code/server.py

EXPOSE 8000
