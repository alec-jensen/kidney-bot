def ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    return str(n) + suffix

def humanbytes(b: int | float) -> str | None:
    """Return the given bytes as a human friendly KB, MB, GB, or TB string."""
    fb = float(b)
    KB = float(1024)
    MB = float(KB ** 2) # 1,048,576
    GB = float(KB ** 3) # 1,073,741,824
    TB = float(KB ** 4) # 1,099,511,627,776

    if fb < KB:
        return '{} {}'.format(fb,'Bytes' if 0 == fb > 1 else 'Byte')
    elif KB <= fb < MB:
        return f'{fb / KB:.2f} KB'
    elif MB <= fb < GB:
        return f'{fb / MB:.2f} MB'
    elif GB <= fb < TB:
        return f'{fb / GB:.2f} GB'
    elif TB <= fb:
        return f'{fb / TB:.2f} TB'
    return None

assert ordinal(1) == '1st'
assert ordinal(2) == '2nd'
assert ordinal(3) == '3rd'
assert ordinal(4) == '4th'
assert ordinal(11) == '11th'
assert ordinal(21) == '21st'
assert ordinal(22) == '22nd'
assert ordinal(23) == '23rd'

assert humanbytes(1) == '1.0 Byte'
assert humanbytes(1024) == '1.00 KB'
assert humanbytes(1024**2) == '1.00 MB'
assert humanbytes(1024**3) == '1.00 GB'
assert humanbytes(1024**4) == '1.00 TB'
assert humanbytes(1024**5) == '1024.00 TB'
