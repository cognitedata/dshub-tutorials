To run the notebook locally install poetry with https://github.com/python-poetry/poetry, then:

```sh
cp viable_pyproject.toml pyproject.toml
poetry install
```sh

Convert the .py  ->  .ipynb with: 
$ poetry run jupytext --to py template_3dnodes_assets.ipynb

Convert the .py -> .ipyn with: 
$ poetry run  jupytext --to notebook template_3dnodes_assets.py
