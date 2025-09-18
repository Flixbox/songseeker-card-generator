# SongSeeker Card Generator

## Introduction
The SongSeeker Card Generator is a Python script designed to create visual cards based on song data. This tool is part of the [SongSeeker project](https://github.com/andygruber/songseeker), a music guessing game.

## Features
- Generate visual cards for songs.
- PDF output.
- Input data in CSV format.

## Prerequisites
Before you start using the SongSeeker Card Generator, make sure you have Python installed on your system. The script is tested with Python 3.11 and above. You can download and install Python from [here](https://www.python.org/downloads/).

## Installation
Clone the repository to your local machine using the following command:
```bash
git clone https://github.com/andygruber/songseeker-card-generator.git
```
Navigate to the cloned directory:
```bash
cd songseeker-card-generator
```
Install the required Python packages:
```bash
pip install -r requirements.txt
```

## Usage

To run the script, use the following command:

```bash
python .\generatePlayCards.py <input_csv_path> <output_pdf_path> [options]
```

### Options

- `--icon <path_or_url>`: Path or URL to an icon to embed in the QR code (transparent background recommended; up to ~300x300px).
- `--no-mirror-backside`: Disable mirroring of the backside (text) layout. By default, the text side is mirrored to align with front-side cutting.
- `--front-bg <path>`: Path to the background image for the front (QR) side.
- `--back-bg <path>`: Path to the background image for the back (text) side. If you provide backgrounds, front and back images must be the exact same pixel size and DPI.
- `--qr-padding-px <int>`: Override the QR code quiet zone (white border) in pixels. QR spec recommends ~4 modules (~40px with default settings). Reducing too much may impact scan reliability.
- `--shrink-front <percent>`: Shrink percentage for the front (QR) content area. Example: `10` makes content 10% smaller (90% of original inner area).
- `--shrink-back <percent>`: Shrink percentage for the back (text) content area. Example: `15` makes content 15% smaller.

### Example

```bash
python .\generatePlayCards.py .\data\example-youtube-songs.csv .\example.pdf
```

You can also add an icon to the card by using the `--icon` flag:

```bash
# Add icon from a URL
python .\generatePlayCards.py .\data\example-youtube-songs.csv .\example.pdf --icon https://github.com/andygruber/songseeker/blob/main/icons/icon-96x96.png?raw=true

# Add icon from a local file
python .\generatePlayCards.py .\data\example-youtube-songs.csv .\example.pdf --icon ..\songseeker\icons\icon-96x96.png

# Reduce the white QR border (quiet zone) to ~10px
python .\generatePlayCards.py .\data\example-youtube-songs.csv .\example.pdf --qr-padding-px 10

# Use custom front/back backgrounds (same size), custom QR padding, and shrink content areas
python .\generatePlayCards.py .\data\example-youtube-songs.csv .\example.pdf `
	--front-bg .\data\songseeker-qr.jpeg `
	--back-bg .\data\songseeker-text.jpeg `
	--qr-padding-px 40 `
	--shrink-front 10 `
	--shrink-back 20

# Disable backside mirroring (if you don't want mirrored text layout)
python .\generatePlayCards.py .\data\example-youtube-songs.csv .\example.pdf --no-mirror-backside
```

Note on QR padding: By default, QR codes include a 4-module quiet zone for reliable scanning. With default QR sizing, this is about 40px. The `--qr-padding-px` option lets you shrink this (for tighter layout), but setting it too low may reduce scan reliability on some devices.

## CSV Input Format

The input CSV file should have the following format:

*   `Title`: The title of the song.
*   `Artist`: The artist of the song.
*   `Year`: The release year of the song.
*   `URL`: The YouTube URL of the song. If the song does not start at the beginning of the video, you may also add the starting time in seconds to the end of the link, like `?t=16`.
*   `backcol`: (optional) background color of the card

Make sure your CSV file includes headers and the data is separated by commas.

An example can be found in `data/example-youtube-songs.csv`.

## Contributing

Contributions to the SongSeeker Card Generator are welcome. Please ensure to update tests as appropriate.

## License

This project is licensed under the AGPL-3.0 license - see the LICENSE file for details.