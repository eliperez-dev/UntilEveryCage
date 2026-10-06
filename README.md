# Until Every Cage is Empty

An interactive, data-driven map exposing the **global** infrastructure of animal exploitation.
[Live website.](https://www.untileverycage.org/)

![alt text](https://github.com/eliperez-dev/UntilEveryCage/blob/master/static/assets/icon.png)

### Their Power is Secrecy. Our Power is Information.

The animal agriculture industry's power is built on a foundation of propaganda and secrecy. This project is a tool designed to shatter that secrecy. It is not a directory; it is a blueprint of an industrial atrocity. By consolidating publicly available data into a single, accessible map, we aim to provide a resource for activists, journalists, and researchers to investigate, document, and ultimately dismantle this system of violence.

## Key Features

For a short introduction to the project's standards, read the [ethics summary](docs/ETHICS-SUMMARY.md); the [full policy](docs/ETHICS.md) remains authoritative.

Contributor and data work is governed by [docs/ETHICS.md](docs/ETHICS.md), including source transparency, privacy, and correction/removal requirements. Outstanding implementation work is tracked in the [policy checklist](docs/governance/policy-implementation-todo.md). Documented requirements are not a claim that every protection is already implemented.

* **Multi-Layer Interactive Map:** Visualizes tens of thousands of facilities across the globe on distinct, toggleable layers.
* **Comprehensive Data:** Integrates multiple public datasets from government bodies worldwide, such as:
    * **Slaughterhouses & Processing Plants** (USDA in the U.S., BVL in Germany, FSA in the UK)
    * **Animal Research Laboratories** (APHIS in the U.S.)
    * **Farms/Breeders, Dealers, & Exhibitors** (APHIS in the U.S.)
* **Detailed Facility Information:** Click on any pin to view detailed information, including names, addresses, certificate numbers, operational data, and license types.
* **Powerful Filtering:** Filter the entire dataset by country and region (state, province, etc.) to focus on local and international infrastructure.
* **Performance Optimized:** The map uses marker clustering to handle thousands of data points smoothly, and the backend utilizes compression for fast initial load times.
* **Shareable Views:** The URL automatically updates as you pan, zoom, and filter, allowing you to share a link to a specific view for collaboration or reporting.

## Technology Stack

This project is built with a focus on performance, transparency, and open-source principles.

* **Backend API:** A high-performance RESTful API written in **Rust** using the **Axum** framework.
* **Frontend:** A client-side application built with vanilla **HTML, CSS, and JavaScript**.
* **Deployment:** Fully Dockerized for easy deployment on any platform (Railway, Fly.io, DigitalOcean, etc.).
* **Mapping Library:** **Leaflet.js** is used for all mapping functionalities, with the **Leaflet.markercluster** plugin for performance.
* **Data Processing:** A series of **Python** scripts using `pandas` and `selenium` were used to download, clean, geocode, and compile the source data.

## Running Locally

This project serves both the API and the frontend from a single high-performance Rust server.

### Prerequisites

* **Rust:** [rust-lang.org](https://www.rust-lang.org/tools/install) (for running without Docker)
* **Docker** (optional, for containerized running)

### Option 1: Running with Cargo (Recommended for dev)

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/eliperez-dev/UntilEveryCage.git
    cd UntilEveryCage
    ```

2.  **Run the server:**
    The server will compile and start listening on port 8000.
    ```bash
    cargo run
    ```

3.  **View the app:**
    Open [http://localhost:8000](http://localhost:8000) in your browser.

### Option 2: Running with Docker

1.  **Build the image:**
    ```bash
    docker build -t uec-api .
    ```

2.  **Run the container:**
    ```bash
    docker run -p 8000:8000 uec-api
    ```

3.  **View the app:**
    Open [http://localhost:8000](http://localhost:8000) in your browser.

## Deployment

This project includes a `Dockerfile` optimized for production (multi-stage build). You can deploy it to any provider that supports Docker.


## How to Contribute

This is a living project, and collaboration is vital to its success. We welcome contributions of all kinds.

* **Contributing International Data:** A primary goal is to expand our global coverage. If you know of a public, official dataset for your country, please open an "Issue" with a link to the source. We welcome help in sourcing, cleaning, and integrating new datasets.
* **Reporting Bugs or Data Errors:** Use GitHub issues for software bugs. For record corrections or privacy/removal requests, use the site's Contribute form or the project email below.
* **Suggesting Features:** Have an idea for a new feature? We'd love to hear it. Open an "Issue" and label it as an "enhancement."
* **Contributing Code:** If you are a developer, feel free to fork the repository and submit a pull request with your changes. Please try to adhere to the existing code style.

## License

The project's source code is licensed under the **GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)**, as stated in its source headers. See [LICENSE](LICENSE). Dependencies and third-party assets retain their own licenses and notices.

AGPL is a copyleft software license. When a modified version supports remote network interaction, section 13 requires an offer of its Corresponding Source to those users. Distribution obligations also apply; the license text defines their scope.

The project's compilation rights are licensed separately under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/); see [DATA_LICENSE](DATA_LICENSE). This covers rights held by the project, not every upstream record or linked document. Preserve source-specific terms and attribution. Public-domain material remains public domain. This noncommercial data license is separate from the open-source software license and does not permit unrestricted commercial reuse of the compilation.

The [license and source-rights review](docs/architecture/source-rights-decisions.md#license-alignment-review-2026-10-05) records the verified scope and remaining release checks.

## Acknowledgements

This project stands on the shoulders of giants and is inspired by the vital work of other activist projects, including:

* [FinalNail.com](https://finalnail.com/)
* [ADAPTT](https://www.adaptt.org/)
* The countless activists and undercover investigators who risk their safety to expose the truth.
* The open-source contributors who help expand this project's reach by adding data from around the world.

## Contact

For questions, suggestions, or to contribute directly, please send a secure email to: **untileverycageproject@protonmail.com**

### Until every cage is empty
