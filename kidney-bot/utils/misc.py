def ordinal(n: int):
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    return str(n) + suffix

def humanbytes(B):
    """Return the given bytes as a human friendly KB, MB, GB, or TB string."""
    B = float(B)
    KB = float(1024)
    MB = float(KB ** 2) # 1,048,576
    GB = float(KB ** 3) # 1,073,741,824
    TB = float(KB ** 4) # 1,099,511,627,776

    if B < KB:
        return '{0} {1}'.format(B,'Bytes' if 0 == B > 1 else 'Byte')
    elif KB <= B < MB:
        return '{0:.2f} KB'.format(B / KB)
    elif MB <= B < GB:
        return '{0:.2f} MB'.format(B / MB)
    elif GB <= B < TB:
        return '{0:.2f} GB'.format(B / GB)
    elif TB <= B:
        return '{0:.2f} TB'.format(B / TB)

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