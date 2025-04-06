const path = require('path');
const fs = require('fs');

const HtmlWebpackPlugin = require('html-webpack-plugin');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');

// Define your JS entry points
const entries = {
    index: '/static/js/index.js',
    archives: '/static/js/archives.js',
    play_recording: '/static/js/play_recording.js',
    play_live: '/static/js/play_live.js',
    broadcasting_page: '/static/js/broadcasting_page.js',
    broadcasting_guide: '/static/js/broadcasting_guide.js',
    listeners_page: '/static/js/listeners_page.js',
    privacy: '/static/js/privacy.js',
    faq: '/static/js/faq.js',
    error: '/static/js/error.js',
};

// Generate HTMLWebpackPlugin instances dynamically for each entry
const htmlPlugins = Object.keys(entries)
    .map(entryName => {
        const templatePath = path.resolve(__dirname, `./templates/${entryName}.html`);
        if (fs.existsSync(templatePath)) {
            return new HtmlWebpackPlugin({
                template: templatePath, // Use template for the specific entry
                filename: `html/${entryName}.html`, // Output HTML in `dist/html`
                chunks: [entryName], // Link the entry's JS and CSS to this HTML
            });
        } else {
            console.warn(`Warning: Template for ${entryName} does not exist. Skipping...`);
            return null;
        }
    })
    .filter(Boolean); // Filter out null entries

module.exports = {
    entry: entries, // JavaScript entry points
    output: {
        filename: 'static/js/[name].bundle.js', // JS output in `dist/static/js`
        path: path.resolve(__dirname, 'dist'),
        publicPath: '/dist/', // Adjust public path if needed
    },
    mode: 'production', // Use 'development' during local dev if needed
    module: {
        rules: [
            // JavaScript loader
            {
                test: /\.js$/,
                exclude: /node_modules/,
                use: {
                    loader: "babel-loader",
                },
            },
            // CSS loader
            {
                test: /\.css$/,
                use: [MiniCssExtractPlugin.loader, 'css-loader'], // Extract CSS to separate files
            },
            // Assets loader (e.g., images, fonts)
            {
                test: /\.(png|jpe?g|gif|svg|woff2?|eot|ttf|otf)$/i,
                type: 'asset/resource',
                generator: {
                    filename: 'static/assets/[name][ext]', // Save assets in `dist/static/assets`
                },
            },
        ],
    },
    plugins: [
        // Extract CSS into separate files
        new MiniCssExtractPlugin({
            filename: 'static/css/[name].bundle.css', // CSS output in `dist/static/css`
        }),
        ...htmlPlugins, // Include dynamically generated HTML plugins
    ],
};
