To run the notebook locally install poetry with https://github.com/python-poetry/poetry, then:

```sh
cp viable_pyproject.toml pyproject.toml
poetry install
```

Convert .py  ->  .ipynb with: 
```sh
poetry run jupytext --to py template_3dnodes_assets.ipynb
```

Convert .py -> .ipyn with: 
```sh
poetry run  jupytext --to notebook template_3dnodes_assets.py
```
