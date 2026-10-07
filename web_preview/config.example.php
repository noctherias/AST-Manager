<?php
declare(strict_types=1);

// Generate both values independently for every installation. Never commit the
// productive config.php. The setup hash is SHA-256 of the one-time setup code.
const AST_SETUP_TOKEN_HASH = 'REPLACE_WITH_SHA256_SETUP_TOKEN';
const AST_LOGIN_PEPPER = 'REPLACE_WITH_RANDOM_64_CHARACTER_HEX_VALUE';
