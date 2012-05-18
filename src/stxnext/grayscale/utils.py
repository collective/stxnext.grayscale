# -*- coding: utf-8 -*-
import os
import re
from PIL import Image
from StringIO import StringIO

from zope.app.component.hooks import getSite
from zope.component import queryMultiAdapter
from zope.contentprovider.interfaces import ContentProviderLookupError
from Products.CMFCore.FSPageTemplate import FSPageTemplate
from Products.Five import BrowserView
from Products.PythonScripts.PythonScript import PythonScript

from stxnext.grayscale import log
from stxnext.grayscale.config import TYPE, THEME

COLOR_PATTERN = re.compile(r"#[a-fA-F0-9]{6}|#[a-fA-F0-9]{3}|rgba?\(.+?\)|color:\s*(?:\w+)", re.M | re.I)

# most popular css color names and their grayscale versions in css notation.
KWRD_MAP = {
  'blue'   : '#1d1d1d',
  'gray'   : '#808080',
  'green'  : '#969696',
  'orange' : '#8c8c8c',
  'purple' : '#555555',
  'red'    : '#4c4c4c',
  'silver' : '#c0c0c0',
  'yellow' : '#aaaaaa',
  }

def transform_style_properties(text):
    """
    Converts the occurances of the color definitions
    to gray scale equivalents
    """
    matches = COLOR_PATTERN.findall(text)
    for match in set(matches):
        converted_match = transform_value(match)
        text = text.replace(match, converted_match)
    return text

def transform_value(color_str):
    """
    Transforms a single color value given
    in any string format to a relevant grayscale
    representation.
    """
    color_val = color_str.split(':')[-1].lower().strip(' ;')
    if color_val in KWRD_MAP:
        return 'color: %s' % KWRD_MAP[color_val]
    elif not color_str.startswith('color'):
        if color_val.startswith('#'):
            tup_val = hex_to_tuple(color_val)
        elif color_val.startswith('rgba'):
            return rgba_grayscale(color_val)
        elif color_val.startswith('rgb'):
            tup_val = rgb_to_tuple(color_val)
        else:
            return color_str
        return tuple_to_hex(grayscale_tuple(tup_val))
    else:
        return color_str

def grayscale_tuple(tup):
    """
    Takes a 3-tuple and returns a 3-tuple,
    with the valu of the input color converted
    to grayscale
    """
    gray = 0.299 * tup[0] + 0.587 * tup[1] + 0.114 * tup[2]
    gray = int(round(gray))
    return (gray, gray, gray)

def hex_to_tuple(text):
    """
    Transform #rrggbb notation of color 
    to 3-tuple (r, g, b)
    """
    colorstring = text.strip()
    # remove trailing "#"
    colorstring = colorstring.lstrip('#')
    if len(colorstring) == 3:
        r, g, b = (colorstring[0] * 2, colorstring[1] * 2, colorstring[2] * 2)
    elif len(colorstring) == 6:
        r, g, b = colorstring[:2], colorstring[2:4], colorstring[4:]
    else:
        raise ValueError, "input #%s is not in #RRGGBB format" % colorstring
    return tuple([int(x, 16) for x in (r, g, b)])

def rgb_to_tuple(text):
    """
    Transforms rgb(x,x,x) both in decimal and %
    notation of color to 3-tuple (r, g, b)
    """
    numbers = re.findall(r'\d+', text)
    if '%' in text:
        return tuple([int((int(x)/100.0) * 255) for x in numbers])
    else:
        return tuple([int(x) for x in numbers])

def rgba_grayscale(text):
    """
    Replaces x, y, z colors in rgba(x,y,z,a) with coresponding grayscale values
    """
    tup_val = rgb_to_tuple(text)
    rgb_grayscale_tup = grayscale_tuple(tup_val[:3])
    rgba_grayscale_tup = rgb_grayscale_tup + tup_val[3:5]
    return "rgba(%d, %d, %d, %d.%d)" % rgba_grayscale_tup

def tuple_to_hex(tup):
    """
    Transforms 3-tuple with colors to 
    #RRGGBB html notation.
    """
    return '#%02x%02x%02x' % tup

def image_to_grayscale(image_data, path):
    """
    Converts image data to grayscale using PIL library 
    """
    try:
        imagestring = StringIO(image_data)
        image_file = Image.open(imagestring)
        converted = image_file.convert('RGBA')
        converted = converted.convert('LA')
        res = StringIO()
        converted.save(res, format='PNG')
        return res.getvalue()
    except IOError, err:
        log.error('Error while transforming image: %s : %s' % (path, err))
        return image_data

def add_bodyclass(html_text):
    """
    Applies the 'gray-scale' css class on body tag 
    """
    bodymatches = re.findall(r"<body.*>", html_text, re.I)
    for bodytag in bodymatches:
        if 'class' in bodytag:
            for css_classs in re.findall(r"class\s*=\s*[\'\"](.*)[\'\"]", bodytag, re.I):
                modified_bodytag = bodytag.replace(css_classs, ' '.join((css_classs, 'gray-style')))
        else:
            modified_bodytag = bodytag.replace('>', ' class="gray-style">')
        html_text = html_text.replace(bodytag, modified_bodytag)
    return html_text

def get_resource(request, response, filename):
    """
    Returns the data of the resource cached
    in the file system
    """
    site = getSite()
    cached_file = site.restrictedTraverse(str('/++%s++%s/%s' % (TYPE, THEME, filename)))
    return cached_file(REQUEST=request, RESPONSE=response).read()

def store_resource(filename, data):
    """
    Stores the data of the resource in the
    file system
    """
    site = getSite()
    location = site.restrictedTraverse(str('/++%s++%s' % (TYPE, THEME))).directory
    fs_file = open(os.path.join(location, filename), "w")
    try:
        fs_file.write(data)
    finally:
        fs_file.close()

def render_object_html(obj, request):
    """
    Returns rendered html for given content object
    """
    published = request.get('PUBLISHED')
    if isinstance(published, (BrowserView, FSPageTemplate, PythonScript)):
        try:
            return published() or ''
        except NotFound:
            log.error("Resource '%s' not found" % repr(obj))
            return ''
    
    def_page_id = obj.getDefaultPage()
    if def_page_id:
        def_page = obj[def_page_id]
        return render_object_html(def_page, request)

    view_name = obj.getLayout()
    view = queryMultiAdapter((obj, request), name=view_name)
    if view:
        try:
            return view.context() or ''
        except ContentProviderLookupError:
            pass

    view = obj.restrictedTraverse(view_name, None)
    if view:
        try:
            return view.context() or ''
        except AttributeError:
            return view() or ''

    try:
        return obj()
    except AttributeError:
        pass
    return ''
    