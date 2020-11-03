#!/bin/bash

# Denoising mariner6.jpg
counter=16
total=""
while [ $counter -le 300 ]
do
    command1=" eift 0 $counter"
    command2=" eift $counter 0"
    total="${total} ${command1} ${command2}"
    ((counter=counter+4))
done

python main.py mariner6.jpg delta f r 4 \
$total \
eift 118 100 eift 94 35 eift 132 59 eift 204 32 eift 222 472 eift 123 438 eift 85 417 eift 97 377 \
eift 124 370 eift 28 406 eift 14 443 eift 110 479 eift 598 118 eift 9 101 eift 94 104 \
i oi cli_test_results/denoised_mariner.png oift cli_test_results/marinerft_test.png

# Denoising canvas.jpg
counter=0
total=""
while [ $counter -le 84 ]
do
    command1=" eift $((42+$counter)) 0"
    command2=" eift 0 $((42+$counter))"
    total="${total} ${command1} ${command2}"
    ((counter=counter+4))
done

python main.py canvas.jpg delta f r 4 \
$total \
i oi cli_test_results/denoised_canvas.png oift cli_test_results/canvasft_test.png

# Denoising moon.png
python main.py moon.jpg delta f r 10 \
eift 0 30 eift 0 45 eift 0 60 eift 0 75 eift 0 90 eift 0 105 eift 0 120 eift 0 135 \
i oi cli_test_results/denoised_moon.png oift cli_test_results/moonft_test.png