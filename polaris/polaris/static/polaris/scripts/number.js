/*
* The source code below is adapted from https://github.com/BrightspaceUI/intl
*
* The main difference between the original source and the code below is how
* the target language is selected. In @brightspace-ui/intl, the language was
* derived from the 'lang' attribute of the top-level <html> tag, whereas the
* code expects the language to be passed a parameter to the function called.
*/

const defaultLocale = 'en';
const supportedBaseLocales = ['ar', 'cy', 'da', 'de', 'en', 'es', 'fr', 'ja', 'ko', 'nl', 'pt', 'sv', 'tr', 'zh'];
const supportedLocales = [
  'ar-sa',
  'cy-gb',
  'da-dk',
  'de-de',
  'en-us',
  'en-ca',
  'en-gb',
  'es-es',
  'es-mx',
  'fr-ca',
  'fr-fr',
  'fr-on',
  'ja-jp',
  'ko-kr',
  'nl-nl',
  'pt-br',
  'sv-se',
  'tr-tr',
  'zh-cn',
  'zh-tw'
];

function validateFormatValue(value) {
  if (value === undefined || value === null) {
    return 0;
  }
  if (typeof value === 'string') {
    value = parseFloat(value);
  }
  if (isNaN(value) || typeof value !== 'number') {
    throw new RangeError('value is out of range.');
  }
  return value;
}

function formatPositiveInteger(value, descriptor, useGrouping) {
  value = Math.floor(value);

  if (!useGrouping) {
    return value.toString();
  }

  const valueStr = '' + value;
  let ret = '';

  const groupSizes = Array.isArray(descriptor.groupSize) ? descriptor.groupSize : [descriptor.groupSize];
  let currentGroupSizeIndex = -1;
  const maxGroupSizeIndex = groupSizes.length - 1;
  let currentGroupSize = 0;
  let groupEnd = valueStr.length;

  while (groupEnd > 0) {
    if (currentGroupSizeIndex < maxGroupSizeIndex) {
      currentGroupSize = groupSizes[++currentGroupSizeIndex];
    }

    let chunk = null;
    if (currentGroupSize === 0) {
      chunk = valueStr.substring(0, groupEnd);
    } else {
      const groupStart = groupEnd - currentGroupSize;
      chunk = valueStr.substring(groupStart, groupEnd);
    }

    // not first or only chunk
    if (groupEnd !== valueStr.length) {
      ret = descriptor.symbols.group + ret;
    }

    ret = chunk + ret;

    groupEnd -= chunk.length;
  }

  return ret;
}

function validateFormatOptions(options) {

  options = options || {};

  options.useGrouping = options.useGrouping !== false;
  if (options.style !== 'decimal' && options.style !== 'percent') {
    options.style = 'decimal';
  }
  options.minimumFractionDigits = validateInteger(
    'minimumFractionDigits',
    options.minimumFractionDigits,
    0,
    0,
    20
  );
  options.maximumFractionDigits = validateInteger(
    'maximumFractionDigits',
    options.maximumFractionDigits,
    Math.max(options.minimumFractionDigits, 3),
    0,
    20
  );

  if (options.minimumFractionDigits > options.maximumFractionDigits) {
    throw new RangeError('maximumFractionDigits value is out of range.');
  }

  return options;

}

function validateInteger(name, value, defaultValue, min, max) {

  if (value === undefined || value === null) {
    value = defaultValue;
  }
  if (typeof value === 'string') {
    value = parseInt(value);
  }
  if (isNaN(value) || typeof value !== 'number' || (min !== undefined && value < min) || (max !== undefined && value > max)) {
    throw new RangeError(name + ' value is out of range.');
  }

  return value;

}

function getNumberDescriptor(language) {
  const subtags = language.split('-');
  const baseLanguage = subtags[0];

  let negativePattern = '-{number}';
  if (baseLanguage === 'ar') {
    negativePattern = '{number}-';
  }

  let percentPattern = '{number} %';
  let percentNegativePattern = '-{number} %';
  switch (baseLanguage) {
    case 'es':
    case 'ja':
    case 'pt':
    case 'zh':
      percentPattern = '{number}%';
      percentNegativePattern = '-{number}%';
      break;
    case 'tr':
      percentPattern = '%{number}';
      percentNegativePattern = '-%{number}';
      break;
  }

  let decimalSymbol = '.';
  let groupSymbol = ',';
  switch (baseLanguage) {
    case 'da':
    case 'de':
    case 'es':
    case 'nl':
    case 'pt':
    case 'tr':
      decimalSymbol = ',';
      groupSymbol = '.';
      break;
    case 'fr':
    case 'sv':
      decimalSymbol = ',';
      groupSymbol = ' ';
      break;
  }

  switch (language) {
    case 'es-mx':
      decimalSymbol = '.';
      groupSymbol = ',';
      break;
  }

  const descriptor = {
    groupSize: 3,
    patterns: {
      decimal: {
        positivePattern: '{number}',
        negativePattern: negativePattern
      },
      percent: {
        positivePattern: percentPattern,
        negativePattern: percentNegativePattern
      }
    },
    symbols: {
      decimal: decimalSymbol,
      group: groupSymbol,
      negative: '-',
      percent: '%'
    }
  };

  return descriptor;
}

function formatDecimal(value, language, options) {

  const descriptor = getNumberDescriptor(language);

  value = validateFormatValue(value);
  options = validateFormatOptions(options);

  const isNegative = value < 0;
  value = Math.abs(value);

  const strValue = new Intl.NumberFormat(
    'en-US', {
      maximumFractionDigits: options.maximumFractionDigits,
      minimumFractionDigits: options.minimumFractionDigits,
      useGrouping: false
    }
  ).format(value);

  let ret = formatPositiveInteger(parseInt(strValue), descriptor, options.useGrouping);

  const decimalIndex = strValue.indexOf('.');
  if (decimalIndex > -1) {
    ret += descriptor.symbols.decimal + strValue.substr(decimalIndex + 1);
  }

  const pattern = isNegative ?
    descriptor.patterns.decimal.negativePattern :
    descriptor.patterns.decimal.positivePattern;

  ret = pattern.replace('{number}', ret);
  if (isNegative) {
    ret = ret.replace('-', descriptor.symbols.negative);
  }
  return ret;

}

function formatNumber(value, language, options) {
  if (options && options.style === 'percent') {
    return formatPercent(value, options, language);
  }
  return formatDecimal(value, language, options);
}

function formatPercent(value, options, language) {

  value = validateFormatValue(value);

  const isNegative = (value < 0);
  value = Math.abs(value) * 100;

  const dec = formatDecimal(value, options, language);

  let percent = isNegative ? descriptor.patterns.percent.negativePattern :
    descriptor.patterns.percent.positivePattern;
  percent = percent.replace('{number}', dec);
  percent = percent.replace('%', descriptor.symbols.percent);
  if (isNegative) {
    percent = percent.replace('-', descriptor.symbols.negative);
  }

  return percent;

}

function parseNumber(value, language) {
  if (value === undefined || value === null) {
    return 0;
  }

  const descriptor = getNumberDescriptor(language);

  value = value.replace(
    new RegExp('\\s|[' + descriptor.symbols.group + ']', 'g'),
    ''
  );
  if (value === '') {
    return 0;
  }

  let ret = '';
  let negative = false;
  let hasDecimal = false;
  let breakout = false;

  for (let i = 0; i < value.length; i++) {
    let c = value.charAt(i);
    switch (c) {
      case descriptor.symbols.decimal:
        ret += !hasDecimal ? '.' : '';
        hasDecimal = true;
        break;
      case descriptor.symbols.negative:
      case '(':
      case ')':
        negative = true;
        break;
      default:
        c = parseInt(c);
        if (!isNaN(c) && c >= 0 && c <= 9) {
          ret += c;
        } else {
          breakout = true;
        }
    }
    if (breakout) {
      break;
    }
  }

  if (ret.length === 0) {
    return NaN;
  }

  ret = parseFloat(ret);

  if (negative) {
    ret = ret * -1;
  }

  return ret;
}
