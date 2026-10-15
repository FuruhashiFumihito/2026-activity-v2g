$out_dir = 'out';
$aux_dir = 'out';
$pdf_mode = 3;
$latex  = 'platex -synctex=1 -halt-on-error -interaction=nonstopmode %O %S';
$dvipdf = 'dvipdfmx %O -o %D %S';
$bibtex = 'pbibtex -kanji=utf8 %O %B';
$max_repeat = 5;
@generated_exts = qw(aux bbl blg idx ind lof lot out toc acn acr alg glg glo gls ist fls log fdb_latexmk snm nav dvi synctex.gz);
$clean_ext = join(' ', @generated_exts);
