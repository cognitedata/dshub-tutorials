from helper import square

def foo():
    return "bar"

def handle(data):
    # You can refer to functions outside the handle function
    bar = foo()
    print(f"Got foo: {bar}")

    value = data["value"]
    squared_value = square(value)
    print(f"Square of {value} is {squared_value}")
    
    return {
        "squaredValue": squared_value,
        "value": value,
        "foo": bar
    }
